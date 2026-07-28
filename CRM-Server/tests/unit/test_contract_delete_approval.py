"""
测试合同删除审批状态拦截

场景八：合同删除后审批记录处理

测试要点：
1. 合同删除使用软删除（deleted_at 字段）
2. 审批中合同不允许删除
3. 审批通过合同不允许删除
4. 审批记录不会因为删除尝试被自动取消或改写
"""
import pytest
from datetime import datetime
from sqlalchemy import create_engine, MetaData
from sqlalchemy.orm import sessionmaker

from app.models.contract import Contract, ContractStatus
from app.models.approval import Approval, ApprovalRecord, ApprovalStatus, ApprovalAction, ApprovalFlow, ApprovalNode
from app.crud.contract import contract_crud
from app.constants.approval_phase import ApprovalPhase


@pytest.fixture(scope="function")
def db_session():
    """创建测试数据库会话（仅包含必要表）"""
    engine = create_engine("sqlite:///:memory:")

    # 创建独立的元数据，只包含测试需要的表
    metadata = MetaData()

    # 创建表结构（手动定义，避免导入所有模型）
    from sqlalchemy import Table, Column, BigInteger, String, Integer, DateTime, Date, Numeric, Text, ForeignKey

    # 合同表
    contracts_table = Table(
        'crm_contracts', metadata,
        Column('id', BigInteger, primary_key=True, autoincrement=True),
        Column('team_id', BigInteger, nullable=False),
        Column('contract_number', String(50), unique=True, nullable=False),
        Column('contract_name', String(255), nullable=False),
        Column('customer_id', BigInteger, nullable=False),
        Column('opportunity_id', BigInteger, nullable=False),
        Column('deal_journey_id', BigInteger, nullable=True),
        Column('signing_contact_id', BigInteger, nullable=False),
        Column('user_count', Integer, nullable=False),
        Column('total_amount', Numeric(12, 2), nullable=False),
        Column('license_type', String(20), nullable=False),
        Column('subscription_years', Integer, nullable=True),
        Column('standard_unit_price', Numeric(10, 2), nullable=False),
        Column('status', String(20), nullable=False),
        Column('approval_phase', String(20), nullable=False, default='draft'),
        Column('signing_date', Date, nullable=True),
        Column('effective_date', Date, nullable=True),
        Column('expiry_date', Date, nullable=True),
        Column('total_paid_amount', Numeric(12, 2), nullable=False, default=0),
        Column('payment_status', String(20), nullable=False, default='UNPAID'),
        Column('contract_file_path', String(500), nullable=True),
        Column('contract_file_name', String(255), nullable=True),
        Column('contract_file_size', BigInteger, nullable=True),
        Column('contract_file_mime_type', String(100), nullable=True),
        Column('created_time', DateTime, nullable=False),
        Column('owner_id', String(100), nullable=False),
        Column('creator_id', String(100), nullable=False),
        Column('last_modified_time', DateTime, nullable=False),
        Column('deleted_at', DateTime, nullable=True),
    )

    # 审批流程表
    approval_flows_table = Table(
        'crm_approval_flows', metadata,
        Column('id', BigInteger, primary_key=True, autoincrement=True),
        Column('team_id', BigInteger, nullable=True),
        Column('flow_name', String(100), nullable=False),
        Column('flow_code', String(50), nullable=False),
        Column('description', Text, nullable=True),
        Column('min_amount', Numeric(12, 2), nullable=True),
        Column('max_amount', Numeric(12, 2), nullable=True),
        Column('license_type', String(20), nullable=True),
        # A3/A5：流程适用单据类型，对齐迁移 012 与 ApprovalFlow 模型
        Column('business_type', String(20), nullable=False, default='CONTRACT'),
        Column('is_active', Integer, nullable=False, default=1),
        Column('created_time', DateTime, nullable=False),
        Column('last_modified_time', DateTime, nullable=False),
    )

    # 审批节点表
    approval_nodes_table = Table(
        'crm_approval_nodes', metadata,
        Column('id', BigInteger, primary_key=True, autoincrement=True),
        Column('team_id', BigInteger, nullable=True),
        Column('flow_id', BigInteger, ForeignKey('crm_approval_flows.id'), nullable=False),
        Column('node_name', String(100), nullable=False),
        Column('node_code', String(50), nullable=False),
        Column('node_order', Integer, nullable=False),
        Column('description', Text, nullable=True),
        Column('approve_role', String(50), nullable=True),
        Column('notify_user_ids', Text, nullable=True),
        Column('is_required', Integer, nullable=False, default=1),
        Column('created_time', DateTime, nullable=False),
    )

    # 审批实例表
    contract_approvals_table = Table(
        'crm_contract_approvals', metadata,
        Column('id', BigInteger, primary_key=True, autoincrement=True),
        Column('team_id', BigInteger, nullable=False),
        Column('contract_id', BigInteger, ForeignKey('crm_contracts.id'), nullable=True),
        # A2/A5：通用业务单据列，对齐迁移 012 与 Approval 模型
        Column('business_type', String(20), nullable=False, default='CONTRACT'),
        Column('business_id', BigInteger, nullable=True),
        Column('flow_id', BigInteger, ForeignKey('crm_approval_flows.id'), nullable=True),
        Column('current_node_id', BigInteger, ForeignKey('crm_approval_nodes.id'), nullable=True),
        Column('status', String(20), nullable=False, default='PENDING'),
        Column('submitter_id', String(100), nullable=False),
        Column('submitter_name', String(100), nullable=True),
        Column('created_time', DateTime, nullable=False),
        Column('updated_time', DateTime, nullable=False),
    )

    # 审批记录表
    contract_approval_records_table = Table(
        'crm_contract_approval_records', metadata,
        Column('id', BigInteger, primary_key=True),  # SQLite 会自动处理 autoincrement
        Column('team_id', BigInteger, nullable=False),
        Column('approval_id', BigInteger, ForeignKey('crm_contract_approvals.id'), nullable=False),
        Column('node_id', BigInteger, ForeignKey('crm_approval_nodes.id'), nullable=True),
        Column('approver_id', String(100), nullable=False),
        Column('approver_name', String(100), nullable=True),
        Column('action', String(20), nullable=False),
        Column('comment', Text, nullable=True),
        Column('created_time', DateTime, nullable=False, default=datetime.now),
    )

    metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def sample_contract(db_session):
    """创建示例合同"""
    contract = Contract(
        id=1,
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
        approval_phase=ApprovalPhase.DRAFT,
        owner_id="user_001",
        creator_id="user_001"
    )
    db_session.add(contract)
    db_session.commit()
    return contract


@pytest.fixture
def sample_approval_flow(db_session):
    """创建示例审批流程"""
    flow = ApprovalFlow(
        id=1,
        team_id=1,
        flow_name="小额合同审批",
        flow_code="SMALL_CONTRACT",
        min_amount=0,
        max_amount=200000,
        is_active=1
    )
    db_session.add(flow)
    db_session.commit()

    node = ApprovalNode(
        id=1,
        team_id=1,
        flow_id=flow.id,
        node_name="销售总监审批",
        node_code="SALES_DIRECTOR",
        node_order=1,
        approve_role="SALES_DIRECTOR"
    )
    db_session.add(node)
    db_session.commit()

    return flow


@pytest.fixture
def sample_approval(db_session, sample_contract, sample_approval_flow):
    """创建示例审批实例"""
    approval = Approval(
        id=1,
        team_id=1,
        contract_id=sample_contract.id,
        # A5：通用业务列，对齐迁移 012 回填语义（business_id = contract_id）
        business_type="CONTRACT",
        business_id=sample_contract.id,
        flow_id=sample_approval_flow.id,
        current_node_id=1,
        status=ApprovalStatus.PENDING,
        submitter_id="user_001",
        submitter_name="测试用户"
    )
    db_session.add(approval)
    db_session.flush()  # 确保 approval.id 获取

    # 使用原生 SQL 插入审批记录（避免 SQLite RETURNING 问题）
    from sqlalchemy import text
    db_session.execute(
        text("INSERT INTO crm_contract_approval_records "
        "(id, team_id, approval_id, node_id, approver_id, approver_name, action, comment, created_time) "
        "VALUES (:id, :team_id, :approval_id, :node_id, :approver_id, :approver_name, :action, :comment, :created_time)"),
        {
            "id": 1,
            "team_id": 1,
            "approval_id": approval.id,
            "node_id": 1,
            "approver_id": "user_001",
            "approver_name": "测试用户",
            "action": ApprovalAction.SUBMIT,
            "comment": "提交审批",
            "created_time": datetime.now()
        }
    )
    db_session.commit()

    return approval


class TestContractDeleteApproval:
    """测试合同删除审批状态拦截"""

    def test_contract_soft_delete(self, db_session, sample_contract):
        """测试合同软删除"""
        # 删除合同
        result = contract_crud.delete(db_session, sample_contract.id)

        assert result is True

        # 查询合同，检查 deleted_at 字段
        contract = db_session.query(Contract).filter(Contract.id == sample_contract.id).first()
        assert contract is not None
        assert contract.deleted_at is not None
        assert contract.status == ContractStatus.DRAFT

    def test_pending_approval_contract_delete_blocked(self, db_session, sample_contract, sample_approval):
        """测试审批中合同不允许删除，审批流程不自动取消"""
        sample_contract.status = ContractStatus.PENDING_REVIEW
        sample_contract.approval_phase = ApprovalPhase.PENDING_REVIEW
        db_session.commit()

        with pytest.raises(ValueError, match="合同审批中或审批通过后不允许删除"):
            contract_crud.delete(db_session, sample_contract.id)

        contract = db_session.query(Contract).filter(Contract.id == sample_contract.id).first()
        approval = db_session.query(Approval).filter(Approval.id == sample_approval.id).first()
        records = db_session.query(ApprovalRecord).filter(
            ApprovalRecord.approval_id == sample_approval.id
        ).all()
        assert contract.deleted_at is None
        assert approval.status == ApprovalStatus.PENDING
        assert len(records) == 1

    def test_approval_records_preserved_after_contract_delete(
        self,
        db_session,
        sample_contract,
        sample_approval
    ):
        """测试审批通过合同不允许删除"""
        # 记录原始审批记录数量
        original_records = db_session.query(ApprovalRecord).filter(
            ApprovalRecord.approval_id == sample_approval.id
        ).all()
        original_count = len(original_records)

        sample_contract.status = ContractStatus.SIGNED
        sample_contract.approval_phase = ApprovalPhase.APPROVED
        sample_approval.status = ApprovalStatus.APPROVED
        db_session.commit()

        with pytest.raises(ValueError, match="合同审批中或审批通过后不允许删除"):
            contract_crud.delete(db_session, sample_contract.id)

        # 查询审批记录，确认数量没有减少
        contract = db_session.query(Contract).filter(Contract.id == sample_contract.id).first()
        records_after_delete = db_session.query(ApprovalRecord).filter(
            ApprovalRecord.approval_id == sample_approval.id
        ).all()
        assert contract.deleted_at is None
        assert len(records_after_delete) == original_count

    def test_approved_approval_phase_blocks_contract_delete(self, db_session, sample_contract):
        """测试审批阶段已通过时，即使业务状态仍是草稿也不允许删除"""
        sample_contract.status = ContractStatus.DRAFT
        sample_contract.approval_phase = ApprovalPhase.APPROVED
        db_session.commit()

        with pytest.raises(ValueError, match="合同审批中或审批通过后不允许删除"):
            contract_crud.delete(db_session, sample_contract.id)

        contract = db_session.query(Contract).filter(Contract.id == sample_contract.id).first()
        assert contract.deleted_at is None

    def test_pending_approval_record_blocks_contract_delete(
        self,
        db_session,
        sample_contract,
        sample_approval
    ):
        """测试最新审批实例审批中时，即使单据字段未同步也不允许删除"""
        sample_contract.status = ContractStatus.DRAFT
        sample_contract.approval_phase = ApprovalPhase.DRAFT
        sample_approval.status = ApprovalStatus.PENDING
        db_session.commit()

        with pytest.raises(ValueError, match="合同审批中或审批通过后不允许删除"):
            contract_crud.delete(db_session, sample_contract.id)

        contract = db_session.query(Contract).filter(Contract.id == sample_contract.id).first()
        assert contract.deleted_at is None

    def test_rejected_contract_can_be_deleted_after_return_to_draft(
        self,
        db_session,
        sample_contract,
        sample_approval
    ):
        """测试审批拒绝并回到草稿后的合同仍可删除"""
        sample_contract.status = ContractStatus.DRAFT
        sample_contract.approval_phase = ApprovalPhase.REJECTED
        sample_approval.status = ApprovalStatus.REJECTED
        db_session.commit()

        result = contract_crud.delete(db_session, sample_contract.id)

        assert result is True
        contract = db_session.query(Contract).filter(Contract.id == sample_contract.id).first()
        assert contract.deleted_at is not None

    def test_deleted_contract_not_in_normal_list(self, db_session, sample_contract):
        """测试已删除的合同不在正常合同列表中"""
        # 删除合同
        contract_crud.delete(db_session, sample_contract.id)

        # 查询合同列表（不包含已删除）
        contracts, total = contract_crud.get_multi(db_session, team_id=1, include_deleted=False)

        # 确认已删除的合同不在列表中
        assert total == 0
        assert len(contracts) == 0

        # 查询合同列表（包含已删除）
        contracts_with_deleted, total_with_deleted = contract_crud.get_multi(
            db_session,
            team_id=1,
            include_deleted=True
        )

        # 确认可以查询到已删除的合同
        assert total_with_deleted >= 1
        assert len(contracts_with_deleted) >= 1

    def test_restore_deleted_contract(self, db_session, sample_contract):
        """测试恢复已删除的合同"""
        # 删除合同
        contract_crud.delete(db_session, sample_contract.id)

        # 确认合同已删除
        contract = db_session.query(Contract).filter(Contract.id == sample_contract.id).first()
        assert contract.deleted_at is not None

        # 恢复合同
        result = contract_crud.restore(db_session, sample_contract.id)
        assert result is True

        # 确认合同已恢复
        contract = db_session.query(Contract).filter(Contract.id == sample_contract.id).first()
        assert contract.deleted_at is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
