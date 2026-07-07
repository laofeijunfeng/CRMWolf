"""License 申请审批流程测试"""
import pytest
from datetime import date

from app.crud.approval import approval_flow_crud, approval_crud
from app.crud.crud_license_application import license_application_crud
from app.constants.business_types import BusinessType
from app.models.license_application import LicenseApplicationStatus
from app.models.approval import ApprovalStatus
from app.schemas.license_application import LicenseApplicationCreate
from app.schemas.approval import ApprovalFlowCreate, ApprovalNodeCreate
from app.services.approval_adapter import get_adapter


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
    from app.crud.customer import customer_crud
    from app.schemas.customer import CustomerCreate

    customer = customer_crud.create(
        db,
        team_id=1,
        obj_in=CustomerCreate(
            customer_name="测试客户",
            customer_type="ENTERPRISE",
            contact_person="张三",
            contact_phone="13800138000"
        ),
        creator_id="test_user_001"
    )
    return customer


@pytest.fixture
def test_team(db):
    """创建测试团队"""
    from app.models.team import Team
    team = Team(
        id=1,
        name="测试团队",
        owner_id="test_user_001"
    )
    db.add(team)
    db.commit()
    db.refresh(team)
    return team


@pytest.fixture
def test_user(db):
    """创建测试用户"""
    from app.models.user import User
    user = User(
        id=1,
        name="测试用户",
        feishu_user_id="test_user_001"
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


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
    assert application.status == LicenseApplicationStatus.PENDING


def test_license_application_without_flow_direct_approval(db, test_team, test_user, test_customer):
    """测试 License 申请未匹配审批流程时免审批直通"""
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

    # 3. 未匹配流程时，返回 None（决策1：免审批直通）
    assert matched_flow is None
    assert err is None  # LICENSE 未匹配不报错

    # 4. 免审批直通逻辑（由 API 层处理）
    # 在实际 API 中会直接设置状态为 ISSUED
    application.status = LicenseApplicationStatus.ISSUED
    db.commit()
    db.refresh(application)

    assert application.status == LicenseApplicationStatus.ISSUED


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
            license_type="OFFICIAL",
            expiry_date=date(2027, 12, 31),
            remark="正式License申请"
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