"""License 申请审批流程测试"""
import pytest
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.types import BigInteger

from app.core.database import Base
from app.crud.approval import approval_flow_crud, approval_crud
from app.crud.crud_license_application import license_application_crud
from app.constants.business_types import BusinessType
from app.models.approval import Approval, ApprovalRecord, ApprovalFlow, ApprovalNode
from app.models.customer import Customer
from app.models.license_application import LicenseApplicationStatus
from app.models.license_application import LicenseApplication
from app.models.approval import ApprovalStatus
from app.schemas.license_application import LicenseApplicationCreate
from app.schemas.approval import ApprovalFlowCreate, ApprovalNodeCreate
from app.services.approval_adapter import get_adapter


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
    return "INTEGER"


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    tables = [
        Customer.__table__,
        LicenseApplication.__table__,
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


def test_license_approval_adapter_registered():
    """测试 License 适配器已注册"""
    adapter = get_adapter(BusinessType.LICENSE)
    assert adapter.business_type == BusinessType.LICENSE
    assert hasattr(adapter, 'on_submit')
    assert hasattr(adapter, 'on_approved')
    assert hasattr(adapter, 'on_rejected')
    assert hasattr(adapter, 'on_cancelled')
    assert hasattr(adapter, 'get_name')
    assert hasattr(adapter, 'get_entity')
    assert hasattr(adapter, 'get_submitter')
    assert hasattr(adapter, 'match_kwargs')


def test_license_application_adapter_methods():
    """测试 License 适配器方法实现"""
    adapter = get_adapter(BusinessType.LICENSE)

    # 测试 match_kwargs 方法（无金额，只有 license_type）
    mock_entity = type('MockEntity', (), {
        'license_type': 'TRIAL',
        'applicant_id': '12345',
        'application_number': 'LIC-202607-001'
    })()

    kwargs = adapter.match_kwargs(mock_entity)
    assert kwargs['amount'] == 0
    assert kwargs['license_type'] == 'TRIAL'

    # 测试 get_submitter 方法
    submitter_id, submitter_name = adapter.get_submitter(mock_entity)
    assert submitter_id == '12345'
    assert submitter_name is None

    # 测试 get_name 方法
    name = adapter.get_name(mock_entity)
    assert name == 'License申请#LIC-202607-001'

    # 测试 None 守卫（E4 规则）
    submitter_id, submitter_name = adapter.get_submitter(None)
    assert submitter_id == ""
    assert submitter_name is None

    name = adapter.get_name(None)
    assert name == "License申请"


@pytest.fixture
def test_customer(db):
    """创建测试客户"""
    customer = Customer(
        team_id=1,
        account_name="测试客户",
        city="上海",
        creator_id="test_user_001",
        owner_id="test_user_001",
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


@pytest.fixture
def test_team(db):
    """创建测试团队"""
    return type("TestTeam", (), {"id": 1})()


@pytest.fixture
def test_user(db):
    """创建测试用户"""
    return type("TestUser", (), {
        "id": 1,
        "name": "测试用户",
        "feishu_user_id": "test_user_001",
    })()


def test_license_application_submit_creates_approval(db, test_team, test_user, test_customer):
    """测试 License 提交时创建审批实例"""
    # 1. 创建审批流程配置（LICENSE 类型）
    flow = approval_flow_crud.create(
        db,
        ApprovalFlowCreate(
            flow_code="LICENSE_DEFAULT",
            flow_name="License申请审批",
            business_type=BusinessType.LICENSE,
            is_active=True,
            nodes=[
                ApprovalNodeCreate(
                    node_name="团队所有者审批",
                    node_code="TEAM_OWNER",
                    node_order=1,
                    approve_role="TEAM_OWNER",
                )
            ]
        ),
        test_team.id
    )

    assert flow.id is not None
    assert flow.business_type == BusinessType.LICENSE
    assert flow.is_active == True

    # 2. 创建 License 申请（草稿）
    application = license_application_crud.create(
        db,
        test_team.id,
        str(test_user.feishu_user_id),
        LicenseApplicationCreate(
            customer_id=test_customer.id,
            license_type="TRIAL",
            expiry_date=date(2026, 12, 31),
            remark="测试申请"
        )
    )

    assert application.id is not None
    assert application.status == LicenseApplicationStatus.DRAFT
    assert application.application_number.startswith("LIC-")

    # 3. 提交申请（接入审批引擎）
    adapter = get_adapter(BusinessType.LICENSE)
    matched_flow, err = approval_flow_crud.match_flow_generic(
        db, BusinessType.LICENSE, test_team.id,
        **adapter.match_kwargs(application)
    )

    assert matched_flow is not None
    assert err is None
    assert matched_flow.id == flow.id

    # 4. 创建审批实例
    approval = approval_crud.create_approval_generic(
        db,
        BusinessType.LICENSE,
        application.id,
        test_team.id,
        matched_flow,
        str(test_user.feishu_user_id),
        test_user.name,
    )

    # 5. 验证审批实例创建成功
    assert approval.id is not None
    assert approval.business_type == BusinessType.LICENSE
    assert approval.business_id == application.id
    assert approval.status == ApprovalStatus.PENDING

    # 6. 验证申请状态已切换为 PENDING
    db.refresh(application)
    assert application.status == LicenseApplicationStatus.PENDING_REVIEW


def test_license_application_without_flow_direct_approval(db, test_team, test_user, test_customer):
    """测试 License 申请未匹配审批流程时返回配置错误"""
    # 1. 创建 License 申请（草稿）
    application = license_application_crud.create(
        db,
        test_team.id,
        str(test_user.feishu_user_id),
        LicenseApplicationCreate(
            customer_id=test_customer.id,
            license_type="TRIAL",
            expiry_date=date(2026, 12, 31),
            remark="测试申请（免审批）"
        )
    )

    assert application.status == LicenseApplicationStatus.DRAFT

    # 2. 匹配审批流程（未配置 LICENSE 流程）
    adapter = get_adapter(BusinessType.LICENSE)
    matched_flow, err = approval_flow_crud.match_flow_generic(
        db, BusinessType.LICENSE, test_team.id,
        **adapter.match_kwargs(application)
    )

    # 3. 未匹配流程时，返回明确错误；License 不再走免审批直通
    assert matched_flow is None
    assert err == "未找到匹配的License审批流程，请联系管理员创建或完善审批流程"

    db.refresh(application)
    assert application.status == LicenseApplicationStatus.DRAFT


def test_license_approval_flow_visible_in_approval_center(db, test_team, test_user, test_customer):
    """测试 License 审批在审批中心可见"""
    # 1. 创建审批流程配置
    flow = approval_flow_crud.create(
        db,
        ApprovalFlowCreate(
            flow_code="LICENSE_OWNER",
            flow_name="License申请-团队所有者审批",
            business_type=BusinessType.LICENSE,
            is_active=True,
            nodes=[
                ApprovalNodeCreate(
                    node_name="团队所有者审批",
                    node_code="TEAM_OWNER",
                    node_order=1,
                    approve_role="TEAM_OWNER",
                )
            ]
        ),
        test_team.id
    )

    # 2. 创建并提交 License 申请
    application = license_application_crud.create(
        db,
        test_team.id,
        str(test_user.feishu_user_id),
        LicenseApplicationCreate(
            customer_id=test_customer.id,
            license_type="TRIAL",
            expiry_date=date(2027, 12, 31),
            remark="试用License申请"
        )
    )

    adapter = get_adapter(BusinessType.LICENSE)
    matched_flow, _ = approval_flow_crud.match_flow_generic(
        db, BusinessType.LICENSE, test_team.id,
        **adapter.match_kwargs(application)
    )

    approval = approval_crud.create_approval_generic(
        db,
        BusinessType.LICENSE,
        application.id,
        test_team.id,
        matched_flow,
        str(test_user.feishu_user_id),
        test_user.name,
    )

    # 3. 验证审批实例可以通过审批中心查询
    # 按业务类型查询审批列表
    approvals, total = approval_crud.get_multi(db, status=ApprovalStatus.PENDING)

    # 4. 验证 License 审批出现在列表中
    license_approvals = [a for a in approvals if a.business_type == BusinessType.LICENSE]
    assert len(license_approvals) >= 1

    # 验证具体的审批实例
    found_approval = next((a for a in license_approvals if a.business_id == application.id), None)
    assert found_approval is not None
    assert found_approval.status == ApprovalStatus.PENDING
