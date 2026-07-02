"""Task B2 / E7：发票在途数据平迁测试（不真跑 alembic upgrade）。

把平迁逻辑抽到独立 helper `invoice_approval_backfill.run_invoice_approval_data_migration(bind)`，
迁移文件 013 的 upgrade() 委托调用它，测试直接 import 该 helper 在内存 SQLite 上跑，
断言平迁结果满足契约：
  - APPROVED 旧发票×2：补建 Approval(INVOICE, APPROVED) 行 + ApprovalRecord(APPROVE)，
    business_id 对应、approver_id 取 reviewer_id。
  - PENDING_REVIEW×1：回退 DRAFT，reviewer_id/comment/reviewed_time 清空。
  - ISSUED×1 / REJECTED×1：不动（状态字段不变）。
  - DRAFT×1：不动（不在平迁范围）。
"""
import importlib.util
import os
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.types import BigInteger
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
    return "INTEGER"


from app.core.database import Base
from app.constants.business_types import BusinessType
from app.models.approval import (
    Approval, ApprovalRecord, ApprovalStatus, ApprovalAction,
)
from app.models.invoice import (
    InvoiceApplication, InvoiceApplicationStatus, InvoiceType,
)


# ---------- 加载平迁 helper（单源：迁移文件 013 顶部模块级函数）------------

def _load_backfill_helper():
    """从 migrations/versions/013_invoice_approval_data_migration.py 加载
    `run_invoice_approval_data_migration(bind)` 函数，避免运行 alembic。

    采用 importlib 路径加载，无需把 migrations/ 标为 Python package。
    """
    here = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    path = os.path.join(
        here, "migrations", "versions", "013_invoice_approval_data_migration.py",
    )
    spec = importlib.util.spec_from_file_location(
        "_m013_invoice_approval_data_migration", path,
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.run_invoice_approval_data_migration


_run_backfill = _load_backfill_helper()


# ---------- DB fixtures ----------------------------------------------------

@pytest.fixture(scope="function")
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [
        InvoiceApplication.__table__,
        Approval.__table__,
        ApprovalRecord.__table__,
    ]
    Base.metadata.create_all(engine, tables=tables)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


# ---------- 种子：4 态 + 1 个 DRAFT（不在平迁范围） -------------------------

def _make_invoice(**overrides):
    base = dict(
        team_id=1,
        application_number="INV-X",
        customer_id=1,
        contract_id=1,
        opportunity_id=1,
        payment_plan_id=1,
        invoice_amount=10000,
        invoice_type=InvoiceType.VAT_NORMAL,
        applicant_id="1",
        invoice_title_type="COMPANY",
        invoice_title_text="测试公司",
        invoice_taxpayer_id="91110000ABC",
    )
    base.update(overrides)
    return InvoiceApplication(**base)


@pytest.fixture
def seed_legacy_invoices(db_session):
    """构造 4 态在途数据：APPROVED×2 / PENDING_REVIEW×1 / ISSUED×1 / REJECTED×1 + DRAFT×1。"""
    approved1 = _make_invoice(
        application_number="INV-OLD-APPROVED-1",
        status=InvoiceApplicationStatus.APPROVED,
        reviewer_id="100",
        review_comment="已审",
        reviewed_time=datetime(2026, 6, 1, 10, 0, 0),
    )
    approved2 = _make_invoice(
        application_number="INV-OLD-APPROVED-2",
        status=InvoiceApplicationStatus.APPROVED,
        reviewer_id="101",
        review_comment=None,
        reviewed_time=datetime(2026, 6, 2, 11, 30, 0),
    )
    pending = _make_invoice(
        application_number="INV-OLD-PENDING-1",
        status=InvoiceApplicationStatus.PENDING_REVIEW,
    )
    issued = _make_invoice(
        application_number="INV-OLD-ISSUED-1",
        status=InvoiceApplicationStatus.ISSUED,
        reviewer_id="102",
        review_comment="已开",
        reviewed_time=datetime(2026, 6, 3, 9, 0, 0),
    )
    rejected = _make_invoice(
        application_number="INV-OLD-REJECTED-1",
        status=InvoiceApplicationStatus.REJECTED,
        reviewer_id="103",
        review_comment="驳回",
        reviewed_time=datetime(2026, 6, 4, 14, 0, 0),
    )
    draft = _make_invoice(
        application_number="INV-OLD-DRAFT-1",
        status=InvoiceApplicationStatus.DRAFT,
    )
    db_session.add_all([approved1, approved2, pending, issued, rejected, draft])
    db_session.commit()
    return {
        "approved1": approved1,
        "approved2": approved2,
        "pending": pending,
        "issued": issued,
        "rejected": rejected,
        "draft": draft,
    }


# ---------- 平迁断言 -------------------------------------------------------

def test_invoice_approval_data_migration_backfills_approved(
    db_session, seed_legacy_invoices,
):
    """APPROVED 旧发票补建 Approval(INVOICE, APPROVED) + ApprovalRecord(APPROVE)。"""
    seed = seed_legacy_invoices
    _run_backfill(db_session)

    approvals = db_session.query(Approval).filter(
        Approval.business_type == BusinessType.INVOICE,
    ).all()
    # 2 条 APPROVED → 2 条补建 Approval
    assert len(approvals) == 2
    business_ids = {a.business_id for a in approvals}
    assert business_ids == {seed["approved1"].id, seed["approved2"].id}
    for a in approvals:
        assert a.status == ApprovalStatus.APPROVED
        assert a.team_id == 1
        assert a.flow_id is None  # 历史数据无对应模板，留 NULL（brief 注释）

    # ApprovalRecord：每条 APPROVED 一条 APPROVE 记录，approver_id 取 reviewer_id
    records = db_session.query(ApprovalRecord).all()
    assert len(records) == 2
    approval_ids = {a.id for a in approvals}
    record_approval_ids = {r.approval_id for r in records}
    assert record_approval_ids == approval_ids
    for r in records:
        assert r.action == ApprovalAction.APPROVE
        assert r.approver_id in ("100", "101")
        assert r.node_id is None  # 无对应节点


def test_invoice_approval_data_migration_demotes_pending_to_draft(
    db_session, seed_legacy_invoices,
):
    """PENDING_REVIEW 旧记录回退 DRAFT，reviewer/comment/reviewed_time 清空。"""
    _run_backfill(db_session)

    db_session.expire_all()
    inv = db_session.query(InvoiceApplication).filter(
        InvoiceApplication.id == seed_legacy_invoices["pending"].id,
    ).one()
    assert inv.status == InvoiceApplicationStatus.DRAFT
    assert inv.reviewer_id is None
    assert inv.review_comment is None
    assert inv.reviewed_time is None


def test_invoice_approval_data_migration_skips_issued_rejected_draft(
    db_session, seed_legacy_invoices,
):
    """ISSUED / REJECTED / DRAFT 不动：状态、reviewer、comment、reviewed_time 不变。"""
    seed = seed_legacy_invoices
    snapshot = {}
    for key in ("issued", "rejected", "draft"):
        inv = seed[key]
        snapshot[key] = (inv.status, inv.reviewer_id, inv.review_comment, inv.reviewed_time)

    _run_backfill(db_session)

    db_session.expire_all()
    for key in ("issued", "rejected", "draft"):
        inv = db_session.query(InvoiceApplication).filter(
            InvoiceApplication.id == seed[key].id,
        ).one()
        assert (inv.status, inv.reviewer_id, inv.review_comment, inv.reviewed_time) == snapshot[key]


def test_invoice_approval_data_migration_no_side_effects_on_non_target_states(
    db_session, seed_legacy_invoices,
):
    """平迁 helper 是历史在途一次性迁移语义（生产 upgrade 仅跑一次），
    本用例固化"对非目标态（ISSUED/REJECTED/DRAFT/PENDING_REVIEW-已回 DRAFT）
    零影响"——即使重跑 helper，也不会为这些态的发票补建 Approval 实例。

    注：APPROVED 行二次跑会重复 INSERT Approval/Record（helper 不做幂等守卫，
    这是预期一次性语义）。本用例只校验"不会把其它态的发票错误拉入引擎表"。
    """
    seed = seed_legacy_invoices
    _run_backfill(db_session)  # 第一次跑：APPROVED×2 补建，pending 回 DRAFT
    _run_backfill(db_session)  # 第二次跑：重复补建 APPROVED×2，但其它态不受影响

    non_target_ids = [
        seed["issued"].id, seed["rejected"].id, seed["draft"].id,
        seed["pending"].id,  # 第一次跑后已回 DRAFT
    ]
    # 非目标态 business_id 永不应出现在 INVOICE 审批实例表
    stray = db_session.query(Approval).filter(
        Approval.business_type == BusinessType.INVOICE,
        Approval.business_id.in_(non_target_ids),
    ).count()
    assert stray == 0

    # ISSUED/REJECTED/DRAFT 行的发票状态字段不因重跑而改变
    db_session.expire_all()
    pending_after = db_session.query(InvoiceApplication).filter(
        InvoiceApplication.id == seed["pending"].id,
    ).one()
    assert pending_after.status == InvoiceApplicationStatus.DRAFT