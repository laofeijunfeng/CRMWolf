"""License 申请审批流程测试"""
import pytest
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.types import BigInteger

from app.core.database import Base
from app.crud.approval import approval_flow_crud, approval_crud
from app.crud import crud_license_application as license_crud_module
from app.crud.crud_license_application import license_application_crud
from app.constants.business_types import BusinessType
from app.models.approval import Approval, ApprovalRecord, ApprovalFlow, ApprovalNode
from app.models.customer import Customer
from app.models.customer_legacy_source_progress import CustomerLegacySourceProgress
from app.models.contract import Contract
from app.models.opportunity import Opportunity
from app.models.product import Product, ProductModule
from app.models.license_application import LicenseApplicationStatus
from app.models.license_application import LicenseApplication
from app.models.approval import ApprovalStatus
from app.schemas.license_application import LicenseApplicationApproveFull, LicenseApplicationInternalCreate
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
        CustomerLegacySourceProgress.__table__,
        Product.__table__,
        ProductModule.__table__,
        Opportunity.__table__,
        Contract.__table__,
        LicenseApplication.__table__,
        ApprovalFlow.__table__,
        ApprovalNode.__table__,
        Approval.__table__,
        ApprovalRecord.__table__,
    ]
    renamed_indexes = []
    for table in tables:
        for index in table.indexes:
            if index.name:
                renamed_indexes.append((index, index.name))
                index.name = f"{table.name}_{index.name}"
    try:
        Base.metadata.create_all(engine, tables=tables)
    finally:
        for index, original_name in renamed_indexes:
            index.name = original_name
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


def _product(db, *, code: str, name: str, is_active: bool = True) -> Product:
    product = Product(team_id=1, code=code, name=name, is_active=is_active, created_by="test_user_001")
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@pytest.fixture
def test_product(db):
    return _product(db, code="APIFOX", name="Apifox")


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


def test_license_application_submit_creates_approval(db, test_team, test_user, test_customer, test_product):
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
        LicenseApplicationInternalCreate(
            customer_id=test_customer.id,
            license_type="TRIAL",
            product_public_id=test_product.public_id,
            authorized_users=10,
            expiry_date=date(2026, 12, 31),
            remark="测试申请"
        )
    )

    assert application.id is not None
    assert application.status == LicenseApplicationStatus.DRAFT

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


def test_license_application_without_flow_direct_approval(db, test_team, test_user, test_customer, test_product):
    """测试 License 申请未匹配审批流程时返回配置错误"""
    # 1. 创建 License 申请（草稿）
    application = license_application_crud.create(
        db,
        test_team.id,
        str(test_user.feishu_user_id),
        LicenseApplicationInternalCreate(
            customer_id=test_customer.id,
            license_type="TRIAL",
            product_public_id=test_product.public_id,
            authorized_users=10,
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


def test_license_approval_flow_visible_in_approval_center(db, test_team, test_user, test_customer, test_product):
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
        LicenseApplicationInternalCreate(
            customer_id=test_customer.id,
            license_type="TRIAL",
            product_public_id=test_product.public_id,
            authorized_users=10,
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


def test_license_info_advances_with_newer_snapshot_only(db, test_customer):
    application = LicenseApplication(
        team_id=1,
        application_number="LIC-SNAPSHOT-1",
        customer_id=test_customer.id,
        expiry_date=date(2027, 12, 31),
        license_type="OFFICIAL",
        authorized_users=10,
        applicant_id="tester",
    )
    db.add(application)
    db.commit()

    license_application_crud.update_customer_license_info(db, 1, application)
    db.refresh(test_customer)
    assert (test_customer.license_expiry_date, test_customer.license_type) == (date(2027, 12, 31), "OFFICIAL")
    progress = db.query(CustomerLegacySourceProgress).filter_by(team_id=1, customer_id=test_customer.id).one()
    assert progress.eligible_revision == 1

    license_application_crud.update_customer_license_info(db, 1, application)
    older = LicenseApplication(
        team_id=1,
        application_number="LIC-SNAPSHOT-OLDER",
        customer_id=test_customer.id,
        expiry_date=date(2026, 12, 31),
        license_type="TRIAL",
        authorized_users=10,
        applicant_id="tester",
    )
    license_application_crud.update_customer_license_info(db, 1, older)
    db.refresh(progress)
    db.refresh(test_customer)
    assert progress.eligible_revision == 1
    assert (test_customer.license_expiry_date, test_customer.license_type) == (date(2027, 12, 31), "OFFICIAL")


def test_permanent_issued_license_wins_over_later_dated_license(db, test_customer):
    permanent = LicenseApplication(
        team_id=1,
        application_number="LIC-PERMANENT",
        customer_id=test_customer.id,
        expiry_date=None,
        is_permanent=True,
        license_type="OFFICIAL",
        authorized_users=50,
        applicant_id="tester",
        status=LicenseApplicationStatus.ISSUED,
    )
    db.add(permanent)
    db.commit()
    license_application_crud.update_customer_license_info(db, 1, permanent)

    dated = LicenseApplication(
        team_id=1,
        application_number="LIC-DATED-LATER",
        customer_id=test_customer.id,
        expiry_date=date(2099, 12, 31),
        license_type="OFFICIAL",
        authorized_users=10,
        applicant_id="tester",
        status=LicenseApplicationStatus.ISSUED,
    )
    db.add(dated)
    db.commit()
    license_application_crud.update_customer_license_info(db, 1, dated)

    db.refresh(test_customer)
    assert (
        test_customer.license_type,
        test_customer.license_authorized_users,
        test_customer.license_expiry_date,
        test_customer.license_is_permanent,
    ) == ("OFFICIAL", 50, None, True)


def test_license_info_rejects_cross_team_application(db, test_customer):
    other_team_application = LicenseApplication(
        team_id=2,
        application_number="LIC-OTHER-TEAM",
        customer_id=test_customer.id,
        expiry_date=date(2028, 1, 1),
        license_type="TRIAL",
        authorized_users=10,
        applicant_id="tester",
    )
    license_application_crud.update_customer_license_info(db, 1, other_team_application)
    db.refresh(test_customer)
    assert test_customer.license_expiry_date is None
    assert db.query(CustomerLegacySourceProgress).count() == 0


def test_issue_rolls_back_application_when_snapshot_progress_fails(db, test_customer, monkeypatch):
    application = LicenseApplication(
        team_id=1,
        application_number="LIC-ATOMIC-ISSUE",
        customer_id=test_customer.id,
        expiry_date=date(2028, 1, 1),
        license_type="TRIAL",
        authorized_users=10,
        applicant_id="tester",
        status=LicenseApplicationStatus.APPROVED,
    )
    db.add(application)
    db.commit()
    approval = Approval(
        team_id=1,
        business_type=BusinessType.LICENSE,
        business_id=application.id,
        status=ApprovalStatus.APPROVED,
        submitter_id="tester",
    )
    db.add(approval)
    db.commit()

    def reject_progress(*_args, **_kwargs):
        raise RuntimeError("progress unavailable")

    monkeypatch.setattr(license_crud_module, "advance_eligible_progress", reject_progress)
    with pytest.raises(RuntimeError, match="progress unavailable"):
        license_application_crud.issue_full(
            db, 1, application.id, LicenseApplicationApproveFull(license_info="企业编号: 123"), "issuer",
        )
    db.rollback()
    db.refresh(application)
    db.refresh(test_customer)
    assert application.status == LicenseApplicationStatus.APPROVED
    assert application.enterprise_id is None
    assert test_customer.license_expiry_date is None
    assert db.query(CustomerLegacySourceProgress).count() == 0


def test_issue_locks_customer_before_changing_application(db, test_customer, monkeypatch):
    application = LicenseApplication(
        team_id=1, application_number="LIC-LOCK-ISSUE", customer_id=test_customer.id,
        expiry_date=date(2028, 1, 1), license_type="TRIAL",
        authorized_users=10, applicant_id="tester", status=LicenseApplicationStatus.APPROVED,
    )
    db.add(application)
    db.commit()
    db.add(Approval(
        team_id=1, business_type=BusinessType.LICENSE, business_id=application.id,
        status=ApprovalStatus.APPROVED, submitter_id="tester",
    ))
    db.commit()

    from app.services.legacy_profile_source import lock_source_customer as real_lock

    locked = []

    def observe_lock(session, *, team_id, customer_id):
        assert application.status == LicenseApplicationStatus.APPROVED
        locked.append(customer_id)
        return real_lock(session, team_id=team_id, customer_id=customer_id)

    monkeypatch.setattr(license_crud_module, "lock_source_customer", observe_lock, raising=False)
    license_application_crud.issue_full(
        db, 1, application.id, LicenseApplicationApproveFull(license_info="企业编号: 123"), "issuer",
    )
    assert locked == [test_customer.id]
    assert application.status == LicenseApplicationStatus.ISSUED
    assert db.query(CustomerLegacySourceProgress).filter_by(
        team_id=1, customer_id=test_customer.id,
    ).one().eligible_revision == 1


def _official_contract(db, customer, product):
    opportunity = Opportunity(
        team_id=1, opportunity_number="OPP-LIC-1", opportunity_name="私有化采购", customer_id=customer.id,
        product_id=product.id if product is not None else None, total_amount=100000, user_count=50,
        unit_price=2000, license_type="SUBSCRIPTION", purchase_type="NEW",
        expected_closing_date=date(2026, 12, 1), owner_id="test_user_001", creator_id="test_user_001",
    )
    db.add(opportunity)
    db.flush()
    contract = Contract(
        team_id=1, contract_number="CON-LIC-1", contract_name="私有化合同", customer_id=customer.id,
        opportunity_id=opportunity.id, user_count=50, total_amount=100000, license_type="SUBSCRIPTION",
        standard_unit_price=2000, owner_id="test_user_001", creator_id="test_user_001",
    )
    db.add(contract)
    db.commit()
    return contract


def _create(db, customer, **overrides):
    fields = {
        "customer_id": customer.id,
        "license_type": "TRIAL",
        "authorized_users": 10,
        "expiry_date": date(2027, 12, 31),
    } | overrides
    return license_application_crud.create(db, 1, "test_user_001", LicenseApplicationInternalCreate(**fields))


def test_official_license_follows_contract_opportunity_product_even_if_inactive(db, test_customer, test_product):
    contract_product = _product(db, code="IDP", name="IDP 平台", is_active=False)
    contract = _official_contract(db, test_customer, contract_product)

    application = _create(
        db, test_customer, license_type="OFFICIAL", contract_id=contract.id, product_public_id=test_product.public_id,
    )

    assert (application.product_id, application.product_name) == (contract_product.id, "IDP 平台")


def test_official_license_without_opportunity_product_uses_selected_product(db, test_customer, test_product):
    contract = _official_contract(db, test_customer, None)

    with pytest.raises(ValueError, match="请选择产品"):
        _create(db, test_customer, license_type="OFFICIAL", contract_id=contract.id)
    application = _create(
        db, test_customer, license_type="OFFICIAL", contract_id=contract.id, product_public_id=test_product.public_id,
    )

    assert application.product_name == "Apifox"


def test_trial_license_requires_an_active_product(db, test_customer):
    with pytest.raises(ValueError, match="团队还没有可用产品"):
        _create(db, test_customer)
    inactive = _product(db, code="OLD", name="旧产品", is_active=False)
    with pytest.raises(ValueError, match="请选择启用中的产品"):
        _create(db, test_customer, product_public_id=inactive.public_id)
    with pytest.raises(ValueError, match="产品不存在"):
        _create(db, test_customer, product_public_id="prd_missing")


def test_license_product_name_snapshot_survives_product_rename(db, test_customer, test_product):
    application = _create(db, test_customer, product_public_id=test_product.public_id)
    test_product.name = "Apifox 新版"
    db.commit()
    db.refresh(application)

    assert application.product_name == "Apifox"
