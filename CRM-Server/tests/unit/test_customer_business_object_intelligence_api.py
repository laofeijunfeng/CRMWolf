from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.api import contracts as contracts_api
from app.api import deployment as deployment_api
from app.api import invoices as invoices_api
from app.api import license_application as license_application_api
from app.api import opportunities as opportunities_api
from app.api import payments as payments_api
from app.constants.approval_phase import ApprovalPhase
from app.models.approval import ApprovalStatus
from app.models.contract import ContractStatus
from app.models.invoice import InvoiceApplicationStatus
from app.models.license_application import LicenseApplicationStatus
from app.models.payment import PaymentPlanStatus


class _RequestData(SimpleNamespace):
    """Small Pydantic-model stand-in for API inputs used by these unit tests."""

    def model_copy(self, *, update=None):
        values = vars(self).copy()
        values.update(update or {})
        return type(self)(**values)


def _customer() -> SimpleNamespace:
    return SimpleNamespace(
        id=101,
        public_id="cus_101",
        account_name="越秀金融",
        industry=None,
        city="广州",
        address=None,
        company_scale=None,
        status=1,
        owner_id="9",
    )


def _opportunity_relation() -> SimpleNamespace:
    return SimpleNamespace(
        id=301,
        public_id="opp_301",
        opportunity_name="企业版采购",
        owner_id="9",
    )


def _opportunity() -> SimpleNamespace:
    return SimpleNamespace(
        id=301,
        public_id="opp_301",
        opportunity_number="OPP-301",
        team_id=2,
        customer_id=101,
        opportunity_name="企业版采购",
        approval_phase=ApprovalPhase.APPROVED.value,
        current_stage_name="POC",
        current_stage_snapshot_id=None,
        current_win_probability=60,
        total_amount=Decimal("120000"),
        user_count=100,
        unit_price=Decimal("1200"),
        subscription_years=1,
        decision_maker_count=2,
        expected_closing_date=date(2026, 12, 31),
        procurement_stage_id=3,
        win_probability=60,
        purchase_type="NEW",
        license_type="SUBSCRIPTION",
        owner_id="9",
        creator_id="9",
        status=0,
        deal_journey_id=None,
        loss_reason=None,
        actual_amount=None,
        actual_closing_date=None,
        created_time=datetime(2026, 8, 29, 10, 0),
        last_modified_time=datetime(2026, 8, 29, 10, 0),
        version=1,
        procurement_method_id=2,
    )


def _contract() -> SimpleNamespace:
    return SimpleNamespace(
        id=401,
        team_id=2,
        customer_id=101,
        opportunity_id=301,
        contract_name="企业版采购合同",
        contract_number="HT-2026-001",
        status=ContractStatus.DRAFT,
        payment_status="UNPAID",
        total_amount=Decimal("120000"),
        standard_unit_price=Decimal("1200"),
        user_count=100,
        license_type="SUBSCRIPTION",
        subscription_years=1,
        signing_contact_id=201,
        owner_id="9",
        creator_id="9",
        created_time=datetime(2026, 8, 29, 10, 0),
        last_modified_time=datetime(2026, 8, 29, 10, 0),
        signing_date=None,
        effective_date=None,
        expiry_date=None,
        contract_file_path=None,
        contract_file_name=None,
        contract_file_size=None,
        contract_file_mime_type=None,
        customer=_customer(),
        opportunity=_opportunity_relation(),
    )


def _payment_plan() -> SimpleNamespace:
    return SimpleNamespace(
        id=501,
        team_id=2,
        contract_id=401,
        stage_name="首付款",
        plan_number="PLAN-001",
        planned_amount=Decimal("50000"),
        due_date=date(2026, 9, 1),
        notes=None,
        status=PaymentPlanStatus.PENDING,
        created_time=datetime(2026, 8, 29, 10, 0),
        last_modified_time=datetime(2026, 8, 29, 10, 0),
        paid_amount=Decimal("0"),
        remaining_amount=Decimal("50000"),
        invoice_count=0,
        invoiced_amount=Decimal("0"),
        contract=_contract(),
        payment_records=[],
    )


def _payment_record() -> SimpleNamespace:
    plan = _payment_plan()
    return SimpleNamespace(
        id=601,
        team_id=2,
        payment_plan_id=501,
        payment_plan=plan,
        record_number="PAY-001",
        actual_amount=Decimal("50000"),
        actual_payer_name="越秀金融",
        payment_date=date(2026, 9, 10),
        proof_attachment=None,
        notes=None,
        confirmation_status="PENDING",
        approval_phase=ApprovalPhase.DRAFT.value,
        approval_id=None,
        approval=None,
        creator_id="9",
        creator_name="张三",
        commission_member_id="9",
        commission_member_name="张三",
        created_time=datetime(2026, 8, 29, 10, 0),
        invoice_title_text=None,
        owner_name=None,
    )


def _invoice_application() -> SimpleNamespace:
    return SimpleNamespace(
        id=701,
        team_id=2,
        customer_id=101,
        application_number="INV-20260802-0001",
        invoice_amount=Decimal("50000"),
        invoice_type="VAT_SPECIAL",
        status="DRAFT",
        approval_phase=ApprovalPhase.DRAFT.value,
        invoice_title_text="越秀金融科技有限公司",
        invoice_number=None,
        contract_id=401,
        opportunity_id=301,
        payment_plan_id=501,
        issued_time=None,
    )


def _invoice_title() -> SimpleNamespace:
    return SimpleNamespace(
        id=801,
        team_id=2,
        customer_id=101,
        title_type="COMPANY",
        title="越秀金融科技有限公司",
        taxpayer_id="91440101MA00000000",
        bank_name="招商银行",
        bank_account="6222000000000000",
        address="广州市天河区",
        phone="020-00000000",
        is_default=False,
        created_time=datetime(2026, 8, 29, 10, 0),
        last_modified_time=datetime(2026, 8, 29, 10, 0),
    )


def _deployment_info() -> SimpleNamespace:
    return SimpleNamespace(
        id=901,
        team_id=2,
        customer_id=101,
        deployment_name="生产环境",
        server_address="https://crm.example.com",
        authorized_users=200,
        is_default=True,
        created_time=datetime(2026, 8, 29, 10, 0),
        last_modified_time=datetime(2026, 8, 29, 10, 0),
        customer=_customer(),
    )


def _license_application() -> SimpleNamespace:
    return SimpleNamespace(
        id=1001,
        team_id=2,
        customer_id=101,
        application_number="LIC-202608-001",
        deployment_info_id=901,
        contract_id=401,
        authorized_users=80,
        expiry_date=date(2027, 8, 2),
        license_type="OFFICIAL",
        enterprise_id=None,
        supported_modules="desktop,web",
        server_license_code=None,
        client_license_code=None,
        remark="正式授权",
        status=LicenseApplicationStatus.DRAFT,
        approval_phase=ApprovalPhase.DRAFT.value,
        applicant_id="9",
        approver_id=None,
        approved_time=None,
        approval_id=None,
        license_code=None,
        created_time=datetime(2026, 8, 29, 10, 0),
        last_modified_time=datetime(2026, 8, 29, 10, 0),
        customer=_customer(),
        deployment_info=_deployment_info(),
        contract=_contract(),
    )


class _FakeQuery:
    def __init__(self, value=None):
        self.value = value

    def filter(self, *criteria):
        return self

    def first(self):
        return self.value


class _FakeResult:
    def __init__(self, value=None):
        self.value = value

    def first(self):
        return self.value


class _FakeDb:
    def delete(self, obj) -> None:
        self.deleted = obj

    def commit(self) -> None:
        self.committed = True

    def refresh(self, obj) -> None:
        self.refreshed = obj

    def rollback(self) -> None:
        self.rolled_back = True

    def query(self, model):
        return _FakeQuery(_customer())

    def execute(self, statement, params=None):
        sql = str(statement)
        if "FROM crm_customers" in sql:
            return _FakeResult(("cus_101", "越秀金融"))
        if "FROM crm_opportunities" in sql:
            return _FakeResult(("opp_301", "企业版采购", "NEW"))
        return _FakeResult()


class _FakeUploadFile:
    filename = "contract.pdf"
    content_type = "application/pdf"

    async def read(self) -> bytes:
        return b"contract"


@pytest.mark.asyncio
async def test_create_opportunity_triggers_business_object_intelligence(monkeypatch) -> None:
    opportunity = _opportunity()
    scheduled = []

    monkeypatch.setattr(
        opportunities_api, "check_customer_edit_permission", lambda customer_id, team_id, current_user, db: _customer()
    )
    monkeypatch.setattr("app.crud.user.user_crud.get_by_id", lambda db, user_id: SimpleNamespace(name="张三"))
    monkeypatch.setattr(
        opportunities_api.approval_transaction_manager,
        "create_with_approval",
        lambda **kwargs: (opportunity, SimpleNamespace(), None),
    )
    monkeypatch.setattr(
        opportunities_api.opportunity_crud, "log_created", lambda db, entity, submitter_id, team_id: None
    )

    async def fake_send_notification(*args, **kwargs):
        return None

    monkeypatch.setattr(
        opportunities_api.approval_transaction_manager,
        "send_notification",
        fake_send_notification,
    )

    async def fake_trigger(db, change):
        scheduled.append(change)

    monkeypatch.setattr(opportunities_api, "_trigger_opportunity_intelligence_refresh", fake_trigger)

    result = await opportunities_api.create_opportunity(
        SimpleNamespace(
            customer_id=101, total_amount=Decimal("120000"), license_type=SimpleNamespace(value="SUBSCRIPTION")
        ),
        team_id=2,
        current_user=SimpleNamespace(id=9),
        db=_FakeDb(),
    )

    assert result.id == "opp_301"
    assert scheduled[0].source_type == "opportunity"
    assert scheduled[0].source_id == 301
    assert scheduled[0].change_type == "created"


@pytest.mark.asyncio
async def test_update_opportunity_triggers_business_object_intelligence(monkeypatch) -> None:
    opportunity = _opportunity()
    scheduled = []

    monkeypatch.setattr(opportunities_api, "_ensure_opportunity_not_pending", lambda db, opportunity, team_id: None)
    monkeypatch.setattr(opportunities_api.opportunity_crud, "update", lambda db, db_obj, obj_in: opportunity)

    async def fake_trigger(db, change):
        scheduled.append(change)

    monkeypatch.setattr(opportunities_api, "_trigger_opportunity_intelligence_refresh", fake_trigger)

    result = await opportunities_api.update_opportunity(
        301,
        SimpleNamespace(),
        db_opportunity=opportunity,
        current_user=SimpleNamespace(id=9),
        db=_FakeDb(),
    )

    assert result.id == "opp_301"
    assert scheduled[0].source_type == "opportunity"
    assert scheduled[0].source_id == 301
    assert scheduled[0].change_type == "updated"
    assert scheduled[0].actor_id == "9"


@pytest.mark.asyncio
async def test_move_opportunity_stage_triggers_business_object_intelligence(monkeypatch) -> None:
    opportunity = _opportunity()
    scheduled = []

    monkeypatch.setattr(opportunities_api, "_ensure_opportunity_approved", lambda db, opportunity, team_id: None)
    monkeypatch.setattr(opportunities_api.opportunity_crud, "move_to_stage", lambda **kwargs: opportunity)

    async def fake_trigger(db, change):
        scheduled.append(change)

    monkeypatch.setattr(opportunities_api, "_trigger_opportunity_intelligence_refresh", fake_trigger)

    result = await opportunities_api.move_opportunity_stage(
        301,
        SimpleNamespace(stage_template_id=3),
        db_opportunity=opportunity,
        current_user=SimpleNamespace(id=9),
        db=_FakeDb(),
    )

    assert result["id"] == "opp_301"
    assert scheduled[0].source_type == "opportunity"
    assert scheduled[0].source_id == 301
    assert scheduled[0].change_type == "updated"


@pytest.mark.asyncio
async def test_mark_opportunity_won_triggers_business_object_intelligence(monkeypatch) -> None:
    opportunity = _opportunity()
    scheduled = []

    monkeypatch.setattr(
        opportunities_api,
        "check_opportunity_edit_permission",
        lambda opportunity_id, team_id, current_user, db: opportunity,
    )
    monkeypatch.setattr(opportunities_api, "_ensure_opportunity_approved", lambda db, opportunity, team_id: None)
    monkeypatch.setattr(
        opportunities_api.opportunity_crud, "mark_as_won", lambda db, db_obj, win_data, actor_id: opportunity
    )
    monkeypatch.setattr(opportunities_api.customer_crud, "get_by_id", lambda db, customer_id, team_id: _customer())

    async def fake_trigger(db, change):
        scheduled.append(change)

    async def fake_notify(*args, **kwargs):
        return {"ok": True}

    monkeypatch.setattr(opportunities_api, "_trigger_opportunity_intelligence_refresh", fake_trigger)
    monkeypatch.setattr(opportunities_api.feishu_service, "notify_opportunity_won", fake_notify)

    result = await opportunities_api.mark_opportunity_as_won(
        301,
        SimpleNamespace(actual_amount=Decimal("120000")),
        team_id=2,
        current_user=SimpleNamespace(id=9),
        db=_FakeDb(),
    )

    assert result.id == "opp_301"
    assert scheduled[0].source_type == "opportunity"
    assert scheduled[0].change_type == "updated"


@pytest.mark.asyncio
async def test_mark_opportunity_lost_triggers_business_object_intelligence(monkeypatch) -> None:
    opportunity = _opportunity()
    scheduled = []

    monkeypatch.setattr(
        opportunities_api,
        "check_opportunity_edit_permission",
        lambda opportunity_id, team_id, current_user, db: opportunity,
    )
    monkeypatch.setattr(opportunities_api, "_ensure_opportunity_approved", lambda db, opportunity, team_id: None)
    monkeypatch.setattr(
        opportunities_api.opportunity_crud, "mark_as_lost", lambda db, db_obj, lose_data, actor_id: opportunity
    )
    monkeypatch.setattr(opportunities_api.customer_crud, "get_by_id", lambda db, customer_id, team_id: _customer())

    async def fake_trigger(db, change):
        scheduled.append(change)

    async def fake_notify(*args, **kwargs):
        return {"ok": True}

    monkeypatch.setattr(opportunities_api, "_trigger_opportunity_intelligence_refresh", fake_trigger)
    monkeypatch.setattr(opportunities_api.feishu_service, "notify_opportunity_lost", fake_notify)

    result = await opportunities_api.mark_opportunity_as_lost(
        301,
        SimpleNamespace(loss_reason="预算取消"),
        team_id=2,
        current_user=SimpleNamespace(id=9),
        db=_FakeDb(),
    )

    assert result.id == "opp_301"
    assert scheduled[0].source_type == "opportunity"
    assert scheduled[0].change_type == "updated"


@pytest.mark.asyncio
async def test_delete_opportunity_triggers_business_object_intelligence_after_success(monkeypatch) -> None:
    opportunity = _opportunity()
    scheduled = []

    monkeypatch.setattr(opportunities_api.opportunity_crud, "delete", lambda db, opportunity_id: True)

    async def fake_trigger(db, change):
        scheduled.append(change)

    monkeypatch.setattr(opportunities_api, "_trigger_opportunity_intelligence_refresh", fake_trigger)

    result = await opportunities_api.delete_opportunity(
        301,
        db_opportunity=opportunity,
        current_user=SimpleNamespace(id=9),
        db=object(),
    )

    assert result.message == "删除成功"
    assert scheduled[0].source_type == "opportunity"
    assert scheduled[0].source_id == 301
    assert scheduled[0].change_type == "deleted"
    assert scheduled[0].object_name == "企业版采购"


@pytest.mark.asyncio
async def test_delete_contract_does_not_trigger_business_object_intelligence_when_delete_fails(monkeypatch) -> None:
    contract = _contract()
    scheduled = []

    def fake_delete(db, contract_id):
        raise ValueError("合同不能删除")

    monkeypatch.setattr(contracts_api.contract_crud, "delete", fake_delete)
    monkeypatch.setattr(
        contracts_api,
        "_trigger_contract_intelligence_refresh",
        lambda db, change: scheduled.append(change),
    )

    with pytest.raises(contracts_api.HTTPException):
        await contracts_api.delete_contract(
            401,
            contract=contract,
            current_user=SimpleNamespace(id=9),
            db=object(),
        )

    assert scheduled == []


@pytest.mark.asyncio
async def test_create_contract_triggers_business_object_intelligence(monkeypatch) -> None:
    contract = _contract()
    scheduled = []

    monkeypatch.setattr(
        contracts_api, "check_customer_edit_permission", lambda customer_id, team_id, current_user, db: _customer()
    )
    monkeypatch.setattr(
        contracts_api.opportunity_crud,
        "get_by_id",
        lambda db, opportunity_id, team_id: SimpleNamespace(customer_id=101),
    )
    monkeypatch.setattr(
        contracts_api.opportunity_crud,
        "get_by_public_id",
        lambda db, opportunity_id, team_id: SimpleNamespace(customer_id=101),
    )
    monkeypatch.setattr(
        contracts_api,
        "_get_opportunity_by_public_id_or_404",
        lambda db, opportunity_id, team_id: SimpleNamespace(id=301, customer_id=101),
    )
    monkeypatch.setattr(
        contracts_api.contact_crud, "get_by_id", lambda db, contact_id, team_id: SimpleNamespace(customer_id=101)
    )
    monkeypatch.setattr(
        contracts_api,
        "_parse_contract_payload",
        lambda contract_payload: _RequestData(customer_id=101, opportunity_id="opp_301", signing_contact_id=201),
    )
    monkeypatch.setattr(contracts_api.contract_crud, "create", lambda **kwargs: contract)
    monkeypatch.setattr(contracts_api.file_storage_service, "save_contract_file", lambda **kwargs: "/contracts/401.pdf")
    monkeypatch.setattr(contracts_api.ApprovalService, "submit_for_approval", lambda db, contract_id: None)

    async def fake_trigger(db, change):
        scheduled.append(change)

    monkeypatch.setattr(contracts_api, "_trigger_contract_intelligence_refresh", fake_trigger)

    result = await contracts_api.create_contract(
        contract_payload='{"customer_id":101,"opportunity_id":301,"signing_contact_id":201,"contract_name":"企业版采购合同","user_count":100,"total_amount":120000,"license_type":"SUBSCRIPTION","subscription_years":1}',
        file=_FakeUploadFile(),
        team_id=2,
        current_user=SimpleNamespace(id=9, name="张三"),
        db=_FakeDb(),
    )

    assert result.id == 401
    assert result.customer_id == "cus_101"
    assert scheduled[0].source_type == "contract"
    assert scheduled[0].source_id == 401
    assert scheduled[0].change_type == "created"


@pytest.mark.asyncio
async def test_update_contract_triggers_business_object_intelligence(monkeypatch) -> None:
    contract = _contract()
    scheduled = []

    monkeypatch.setattr(contracts_api.contract_crud, "update", lambda db, db_obj, obj_in: contract)

    async def fake_trigger(db, change):
        scheduled.append(change)

    monkeypatch.setattr(contracts_api, "_trigger_contract_intelligence_refresh", fake_trigger)

    result = await contracts_api.update_contract(
        401,
        SimpleNamespace(),
        contract=contract,
        current_user=SimpleNamespace(id=9),
        db=_FakeDb(),
    )

    assert result.id == 401
    assert result.customer_id == "cus_101"
    assert scheduled[0].source_type == "contract"
    assert scheduled[0].source_id == 401
    assert scheduled[0].change_type == "updated"


@pytest.mark.asyncio
async def test_create_payment_plans_trigger_business_object_intelligence(monkeypatch) -> None:
    plan = _payment_plan()
    scheduled = []

    monkeypatch.setattr(
        payments_api,
        "check_contract_edit_permission",
        lambda contract_id, team_id, current_user, db: SimpleNamespace(status="SIGNED"),
    )
    monkeypatch.setattr(
        payments_api.payment_plan_crud, "batch_create", lambda db, contract_id, plans, creator_id, team_id: [plan]
    )

    async def fake_trigger(db, change):
        scheduled.append(change)

    monkeypatch.setattr(payments_api, "_trigger_payment_plan_intelligence_refresh", fake_trigger)

    result = await payments_api.create_payment_plans(
        401,
        _RequestData(plans=[SimpleNamespace()]),
        team_id=2,
        current_user=SimpleNamespace(id=9),
        db=_FakeDb(),
    )

    assert [item.id for item in result] == [501]
    assert scheduled[0].source_type == "payment_plan"
    assert scheduled[0].source_id == 501
    assert scheduled[0].change_type == "created"


@pytest.mark.asyncio
async def test_update_payment_plan_triggers_business_object_intelligence(monkeypatch) -> None:
    plan = _payment_plan()
    scheduled = []

    monkeypatch.setattr(payments_api, "check_payment_view_permission", lambda plan_id, team_id, current_user, db: plan)
    monkeypatch.setattr(payments_api.payment_plan_crud, "update", lambda db, db_obj, obj_in: plan)

    async def fake_trigger(db, change):
        scheduled.append(change)

    monkeypatch.setattr(payments_api, "_trigger_payment_plan_intelligence_refresh", fake_trigger)

    result = await payments_api.update_payment_plan(
        501,
        SimpleNamespace(),
        team_id=2,
        current_user=SimpleNamespace(id=9),
        db=_FakeDb(),
    )

    assert result.id == 501
    assert scheduled[0].source_type == "payment_plan"
    assert scheduled[0].source_id == 501
    assert scheduled[0].change_type == "updated"


@pytest.mark.asyncio
async def test_create_payment_record_triggers_business_object_intelligence(monkeypatch) -> None:
    record = _payment_record()
    scheduled = []

    monkeypatch.setattr(
        payments_api, "check_payment_view_permission", lambda plan_id, team_id, current_user, db: record.payment_plan
    )
    monkeypatch.setattr(payments_api, "_validate_payment_commission_member", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        payments_api.payment_record_crud,
        "create",
        lambda db, plan_id, record_data, creator_id, creator_name, team_id, **kwargs: record,
    )

    async def fake_trigger(db, change):
        scheduled.append(change)

    monkeypatch.setattr(payments_api, "_trigger_payment_record_intelligence_refresh", fake_trigger)

    result = await payments_api.create_payment_record(
        501,
        SimpleNamespace(commission_member_id="9"),
        team_id=2,
        current_user=SimpleNamespace(id=9, name="张三"),
        db=_FakeDb(),
    )

    assert result.id == 601
    assert scheduled[0].source_type == "payment_record"
    assert scheduled[0].source_id == 601
    assert scheduled[0].change_type == "created"


@pytest.mark.asyncio
async def test_delete_payment_record_triggers_business_object_intelligence_after_success(monkeypatch) -> None:
    record = _payment_record()
    scheduled = []

    monkeypatch.setattr(payments_api.payment_record_crud, "get_by_id", lambda db, record_id, team_id: record)
    monkeypatch.setattr(
        payments_api, "check_payment_view_permission", lambda plan_id, team_id, current_user, db: object()
    )
    monkeypatch.setattr(payments_api.payment_record_crud, "delete", lambda db, record_id, team_id: True)

    async def fake_trigger(db, change):
        scheduled.append(change)

    monkeypatch.setattr(payments_api, "_trigger_payment_record_intelligence_refresh", fake_trigger)

    await payments_api.delete_payment_record(
        601,
        team_id=2,
        current_user=SimpleNamespace(id=9),
        db=object(),
    )

    assert scheduled[0].source_type == "payment_record"
    assert scheduled[0].source_id == 601
    assert scheduled[0].change_type == "deleted"


def test_update_invoice_application_enqueues_business_object_intelligence(monkeypatch) -> None:
    application = _invoice_application()
    scheduled = []

    monkeypatch.setattr(
        invoices_api, "check_invoice_edit_permission", lambda application_id, team_id, current_user, db: application
    )
    monkeypatch.setattr(invoices_api.invoice_application_crud, "update", lambda db, db_obj, obj_in: application)
    monkeypatch.setattr(invoices_api, "_populate_application_info", lambda db, application, team_id: application)
    monkeypatch.setattr(
        invoices_api,
        "_enqueue_invoice_application_intelligence_refresh",
        lambda db, change: scheduled.append(change),
    )

    result = invoices_api.update_invoice_application(
        701,
        SimpleNamespace(),
        team_id=2,
        current_user=SimpleNamespace(id=9),
        db=object(),
    )

    assert result is application
    assert scheduled[0].source_type == "invoice_application"
    assert scheduled[0].source_id == 701
    assert scheduled[0].change_type == "updated"
    assert scheduled[0].actor_id == "9"


def test_delete_invoice_application_enqueues_business_object_intelligence_after_success(monkeypatch) -> None:
    application = _invoice_application()
    scheduled = []

    monkeypatch.setattr(
        invoices_api, "check_invoice_edit_permission", lambda application_id, team_id, current_user, db: application
    )
    monkeypatch.setattr(invoices_api.invoice_application_crud, "delete", lambda db, application_id, team_id: True)
    monkeypatch.setattr(
        invoices_api,
        "_enqueue_invoice_application_intelligence_refresh",
        lambda db, change: scheduled.append(change),
    )

    result = invoices_api.delete_invoice_application(
        701,
        team_id=2,
        current_user=SimpleNamespace(id=9),
        db=object(),
    )

    assert result["message"] == "删除成功"
    assert scheduled[0].source_type == "invoice_application"
    assert scheduled[0].source_id == 701
    assert scheduled[0].change_type == "deleted"
    assert scheduled[0].object_name == "INV-20260802-0001"


def test_delete_invoice_application_does_not_enqueue_when_delete_fails(monkeypatch) -> None:
    application = _invoice_application()
    scheduled = []

    def fake_delete(db, application_id, team_id):
        raise ValueError("发票申请不能删除")

    monkeypatch.setattr(
        invoices_api, "check_invoice_edit_permission", lambda application_id, team_id, current_user, db: application
    )
    monkeypatch.setattr(invoices_api.invoice_application_crud, "delete", fake_delete)
    monkeypatch.setattr(
        invoices_api,
        "_enqueue_invoice_application_intelligence_refresh",
        lambda db, change: scheduled.append(change),
    )

    with pytest.raises(invoices_api.HTTPException):
        invoices_api.delete_invoice_application(
            701,
            team_id=2,
            current_user=SimpleNamespace(id=9),
            db=object(),
        )

    assert scheduled == []


def test_create_invoice_application_enqueues_business_object_intelligence(monkeypatch) -> None:
    application = _invoice_application()
    scheduled = []

    monkeypatch.setattr(
        invoices_api.invoice_application_crud, "create", lambda db, obj_in, applicant_id, team_id: application
    )
    monkeypatch.setattr(invoices_api, "_populate_application_info", lambda db, application, team_id: application)
    monkeypatch.setattr(
        invoices_api,
        "_enqueue_invoice_application_intelligence_refresh",
        lambda db, change: scheduled.append(change),
    )

    result = invoices_api.create_invoice_application(
        SimpleNamespace(),
        team_id=2,
        current_user=SimpleNamespace(id=9),
        db=object(),
    )

    assert result is application
    assert scheduled[0].source_type == "invoice_application"
    assert scheduled[0].source_id == 701
    assert scheduled[0].change_type == "created"


@pytest.mark.asyncio
async def test_mark_invoice_issued_enqueues_business_object_intelligence(monkeypatch) -> None:
    application = _invoice_application()
    application.status = InvoiceApplicationStatus.APPROVED
    issued = _invoice_application()
    issued.status = InvoiceApplicationStatus.ISSUED
    scheduled = []

    monkeypatch.setattr(
        invoices_api.invoice_application_crud, "get_by_id", lambda db, application_id, team_id: application
    )
    monkeypatch.setattr(
        invoices_api.approval_crud,
        "get_by_entity",
        lambda db, business_type, application_id, team_id: SimpleNamespace(
            status=ApprovalStatus.APPROVED, submitter_id="9"
        ),
    )
    monkeypatch.setattr(
        invoices_api.invoice_application_crud,
        "mark_issued",
        lambda db, application_id, team_id, invoice_file_path, invoice_number: issued,
    )
    monkeypatch.setattr(invoices_api, "_populate_application_info", lambda db, application, team_id: application)
    monkeypatch.setattr(
        invoices_api,
        "_enqueue_invoice_application_intelligence_refresh",
        lambda db, change: scheduled.append(change),
    )

    async def fake_notify(**kwargs):
        return {"ok": True}

    monkeypatch.setattr(invoices_api.feishu_notification_service, "notify_approval_issued", fake_notify)

    result = await invoices_api.mark_invoice_issued(
        701,
        file=None,
        invoice_number="FP-001",
        team_id=2,
        current_user=SimpleNamespace(id=9),
        db=object(),
    )

    assert result is issued
    assert scheduled[0].source_type == "invoice_application"
    assert scheduled[0].change_type == "updated"
    assert scheduled[0].payload["status"] == InvoiceApplicationStatus.ISSUED


def test_create_invoice_title_enqueues_business_object_intelligence(monkeypatch) -> None:
    title = _invoice_title()
    scheduled = []

    monkeypatch.setattr(
        invoices_api, "check_customer_edit_permission", lambda customer_id, team_id, current_user, db: _customer()
    )
    monkeypatch.setattr(
        invoices_api.invoice_title_crud, "get_by_taxpayer_id", lambda db, customer_id, taxpayer_id, team_id: None
    )
    monkeypatch.setattr(invoices_api.invoice_title_crud, "create", lambda db, customer_id, obj_in, team_id: title)
    monkeypatch.setattr(
        invoices_api,
        "_enqueue_invoice_business_object_intelligence_refresh",
        lambda db, change: scheduled.append(change),
    )

    result = invoices_api.create_invoice_title(
        customer_id=101,
        title_data=SimpleNamespace(taxpayer_id="91440101MA00000000"),
        team_id=2,
        current_user=SimpleNamespace(id=9),
        db=_FakeDb(),
    )

    assert result.id == 801
    assert result.customer_id == "cus_101"
    assert scheduled[0].source_type == "invoice_title"
    assert scheduled[0].source_id == 801
    assert scheduled[0].change_type == "created"
    assert scheduled[0].payload["has_bank_account"] is True


def test_update_invoice_title_enqueues_business_object_intelligence(monkeypatch) -> None:
    title = _invoice_title()
    scheduled = []

    monkeypatch.setattr(invoices_api.invoice_title_crud, "get_by_id", lambda db, title_id, team_id: title)
    monkeypatch.setattr(
        invoices_api, "check_customer_edit_permission", lambda customer_id, team_id, current_user, db: _customer()
    )
    monkeypatch.setattr(invoices_api.invoice_title_crud, "update", lambda db, db_obj, obj_in: title)
    monkeypatch.setattr(
        invoices_api,
        "_enqueue_invoice_business_object_intelligence_refresh",
        lambda db, change: scheduled.append(change),
    )

    result = invoices_api.update_invoice_title(
        801,
        SimpleNamespace(),
        team_id=2,
        current_user=SimpleNamespace(id=9),
        db=_FakeDb(),
    )

    assert result.id == 801
    assert result.customer_id == "cus_101"
    assert scheduled[0].source_type == "invoice_title"
    assert scheduled[0].change_type == "updated"
    assert scheduled[0].object_name == "越秀金融科技有限公司"


def test_delete_invoice_title_enqueues_business_object_intelligence_after_success(monkeypatch) -> None:
    title = _invoice_title()
    scheduled = []

    monkeypatch.setattr(invoices_api.invoice_title_crud, "get_by_id", lambda db, title_id, team_id: title)
    monkeypatch.setattr(
        invoices_api, "check_customer_edit_permission", lambda customer_id, team_id, current_user, db: None
    )
    monkeypatch.setattr(invoices_api.invoice_title_crud, "delete", lambda db, title_id, team_id: True)
    monkeypatch.setattr(
        invoices_api,
        "_enqueue_invoice_business_object_intelligence_refresh",
        lambda db, change: scheduled.append(change),
    )

    result = invoices_api.delete_invoice_title(
        801,
        team_id=2,
        current_user=SimpleNamespace(id=9),
        db=_FakeDb(),
    )

    assert result["message"] == "删除成功"
    assert scheduled[0].source_type == "invoice_title"
    assert scheduled[0].source_id == 801
    assert scheduled[0].change_type == "deleted"


def test_delete_invoice_title_does_not_enqueue_when_delete_fails(monkeypatch) -> None:
    title = _invoice_title()
    scheduled = []

    monkeypatch.setattr(invoices_api.invoice_title_crud, "get_by_id", lambda db, title_id, team_id: title)
    monkeypatch.setattr(
        invoices_api, "check_customer_edit_permission", lambda customer_id, team_id, current_user, db: None
    )
    monkeypatch.setattr(invoices_api.invoice_title_crud, "delete", lambda db, title_id, team_id: False)
    monkeypatch.setattr(
        invoices_api,
        "_enqueue_invoice_business_object_intelligence_refresh",
        lambda db, change: scheduled.append(change),
    )

    with pytest.raises(invoices_api.HTTPException):
        invoices_api.delete_invoice_title(
            801,
            team_id=2,
            current_user=SimpleNamespace(id=9),
            db=object(),
        )

    assert scheduled == []


def test_create_deployment_info_enqueues_business_object_intelligence(monkeypatch) -> None:
    deployment = _deployment_info()
    scheduled = []

    def fake_enqueue(db, deployment, *, change_type, actor_id):
        change = deployment_api.customer_business_object_intelligence_service.build_change(
            None,
            source_type="deployment_info",
            business_object=deployment,
            change_type=change_type,
            actor_id=actor_id,
        )
        scheduled.append(change)

    monkeypatch.setattr(
        deployment_api, "check_customer_edit_permission", lambda customer_id, team_id, current_user, db: _customer()
    )
    monkeypatch.setattr(deployment_api, "create_deployment_info", lambda db, team_id, obj_in: deployment)
    monkeypatch.setattr(deployment_api, "_enqueue_deployment_intelligence_refresh", fake_enqueue)

    result = deployment_api.create_deployment(
        _RequestData(customer_id=101),
        team_id=2,
        current_user=SimpleNamespace(id=9),
        db=_FakeDb(),
    )

    assert result.id == 901
    assert result.customer_id == "cus_101"
    assert scheduled[0].source_type == "deployment_info"
    assert scheduled[0].source_id == 901
    assert scheduled[0].change_type == "created"
    assert scheduled[0].payload["has_server_address"] is True


def test_set_default_deployment_info_enqueues_business_object_intelligence(monkeypatch) -> None:
    deployment = _deployment_info()
    scheduled = []

    def fake_enqueue(db, deployment, *, change_type, actor_id):
        change = deployment_api.customer_business_object_intelligence_service.build_change(
            None,
            source_type="deployment_info",
            business_object=deployment,
            change_type=change_type,
            actor_id=actor_id,
        )
        scheduled.append(change)

    monkeypatch.setattr(
        deployment_api, "check_customer_edit_permission", lambda customer_id, team_id, current_user, db: _customer()
    )
    monkeypatch.setattr(
        deployment_api, "set_default_deployment_info", lambda db, team_id, customer_id, deployment_id: deployment
    )
    monkeypatch.setattr(deployment_api, "_enqueue_deployment_intelligence_refresh", fake_enqueue)

    result = deployment_api.set_default_deployment(
        901,
        customer_id=101,
        team_id=2,
        current_user=SimpleNamespace(id=9),
        db=_FakeDb(),
    )

    assert result.id == 901
    assert result.customer_id == "cus_101"
    assert scheduled[0].source_type == "deployment_info"
    assert scheduled[0].change_type == "updated"


def test_delete_deployment_info_does_not_enqueue_when_delete_fails(monkeypatch) -> None:
    deployment = _deployment_info()
    scheduled = []

    monkeypatch.setattr(deployment_api, "get_deployment_info", lambda db, team_id, deployment_id: deployment)
    monkeypatch.setattr(
        deployment_api, "check_customer_edit_permission", lambda customer_id, team_id, current_user, db: None
    )
    monkeypatch.setattr(deployment_api, "delete_deployment_info", lambda db, team_id, deployment_id: False)
    monkeypatch.setattr(
        deployment_api,
        "_enqueue_deployment_intelligence_refresh",
        lambda db, change: scheduled.append(change),
    )

    with pytest.raises(deployment_api.HTTPException):
        deployment_api.delete_deployment(
            901,
            team_id=2,
            current_user=SimpleNamespace(id=9),
            db=object(),
        )

    assert scheduled == []


def test_create_license_application_enqueues_business_object_intelligence(monkeypatch) -> None:
    application = _license_application()
    scheduled = []

    def fake_enqueue(db, application, *, change_type, actor_id):
        change = license_application_api.customer_business_object_intelligence_service.build_change(
            None,
            source_type="license_application",
            business_object=application,
            change_type=change_type,
            actor_id=actor_id,
        )
        scheduled.append(change)

    monkeypatch.setattr(
        license_application_api,
        "check_customer_edit_permission",
        lambda customer_id, team_id, current_user, db: _customer(),
    )
    monkeypatch.setattr(
        license_application_api, "create_license_application", lambda db, team_id, obj_in, applicant_id: application
    )
    monkeypatch.setattr(license_application_api, "_enqueue_license_application_intelligence_refresh", fake_enqueue)

    result = license_application_api.create_application(
        _RequestData(customer_id=101),
        team_id=2,
        current_user=SimpleNamespace(id=9),
        db=object(),
    )

    assert result.id == 1001
    assert result.customer_id == "cus_101"
    assert scheduled[0].source_type == "license_application"
    assert scheduled[0].source_id == 1001
    assert scheduled[0].change_type == "created"
    assert scheduled[0].payload["has_supported_modules"] is True
    assert scheduled[0].payload["has_server_license_code"] is False


def test_submit_license_application_enqueues_business_object_intelligence(monkeypatch) -> None:
    existing = _license_application()
    submitted = _license_application()
    submitted.status = LicenseApplicationStatus.PENDING_REVIEW
    scheduled = []
    crud = SimpleNamespace(
        submit=lambda db, team_id, application_id, submitter_id, submitter_name: submitted,
    )

    def fake_enqueue(db, application, *, change_type, actor_id):
        change = license_application_api.customer_business_object_intelligence_service.build_change(
            None,
            source_type="license_application",
            business_object=application,
            change_type=change_type,
            actor_id=actor_id,
        )
        scheduled.append(change)

    monkeypatch.setattr(
        license_application_api, "get_license_application", lambda db, team_id, application_id: existing
    )
    monkeypatch.setattr(
        license_application_api,
        "check_customer_edit_permission",
        lambda customer_id, team_id, current_user, db: _customer(),
    )
    monkeypatch.setattr("app.crud.crud_license_application.license_application_crud", crud)
    monkeypatch.setattr(license_application_api, "_enqueue_license_application_intelligence_refresh", fake_enqueue)

    result = license_application_api.submit_application(
        1001,
        team_id=2,
        current_user=SimpleNamespace(id=9, name="张三"),
        db=object(),
    )

    assert result.id == 1001
    assert result.status == LicenseApplicationStatus.PENDING_REVIEW
    assert scheduled[0].source_type == "license_application"
    assert scheduled[0].change_type == "updated"
    assert scheduled[0].payload["status"] == LicenseApplicationStatus.PENDING_REVIEW


@pytest.mark.asyncio
async def test_issue_license_application_enqueues_business_object_intelligence(monkeypatch) -> None:
    existing = _license_application()
    existing.status = LicenseApplicationStatus.APPROVED
    issued = _license_application()
    issued.status = LicenseApplicationStatus.ISSUED
    issued.server_license_code = "server-secret"
    scheduled = []

    def fake_enqueue(db, application, *, change_type, actor_id):
        change = license_application_api.customer_business_object_intelligence_service.build_change(
            None,
            source_type="license_application",
            business_object=application,
            change_type=change_type,
            actor_id=actor_id,
        )
        scheduled.append(change)

    monkeypatch.setattr(
        license_application_api, "get_license_application", lambda db, team_id, application_id: existing
    )
    monkeypatch.setattr(
        license_application_api.approval_crud, "get_by_entity", lambda db, business_type, application_id, team_id: None
    )
    monkeypatch.setattr(
        license_application_api,
        "issue_license_application_full",
        lambda db, team_id, application_id, issue_data, issuer_id: issued,
    )
    monkeypatch.setattr(license_application_api, "_enqueue_license_application_intelligence_refresh", fake_enqueue)

    result = await license_application_api.issue_application(
        1001,
        SimpleNamespace(),
        team_id=2,
        current_user=SimpleNamespace(id=9),
        db=object(),
    )

    assert result.id == 1001
    assert result.status == LicenseApplicationStatus.ISSUED
    assert scheduled[0].source_type == "license_application"
    assert scheduled[0].change_type == "updated"
    assert scheduled[0].payload["has_server_license_code"] is True
    assert "server-secret" not in scheduled[0].payload.values()


@pytest.mark.asyncio
async def test_update_opportunity_deal_journey_passes_expected_version_and_returns_new_version(monkeypatch) -> None:
    opportunity = _opportunity()
    opportunity.public_id = "opp_301"
    opportunity.opportunity_number = "OPP-301"
    opportunity.deal_journey_id = 11
    opportunity.created_time = datetime(2026, 8, 29, 10, 0)
    opportunity.last_modified_time = datetime(2026, 8, 29, 10, 0)
    opportunity.version = 7
    customer = SimpleNamespace(
        public_id="cus_101",
        account_name="越秀金融",
        industry=None,
        city="广州",
        address=None,
        company_scale=None,
        status=1,
        owner_id="9",
    )
    db = _FakeDb()
    received = {}

    monkeypatch.setattr(opportunities_api, "_ensure_opportunity_not_pending", lambda db, opportunity, team_id: None)
    monkeypatch.setattr(opportunities_api.customer_crud, "get_by_id", lambda db, customer_id, team_id: customer)

    from app.services import deal_journey_service as deal_journey_module

    def fake_associate(db, db_opportunity, **kwargs):
        received.update(kwargs)
        db_opportunity.deal_journey_id = kwargs["deal_journey_id"]
        db_opportunity.version += 1
        return SimpleNamespace(id=kwargs["deal_journey_id"])

    monkeypatch.setattr(deal_journey_module.deal_journey_service, "associate_opportunity", fake_associate)

    result = await opportunities_api.update_opportunity_deal_journey(
        "opp_301",
        opportunities_api.OpportunityDealJourneyUpdate(deal_journey_id=22, expected_version=7),
        db_opportunity=opportunity,
        current_user=SimpleNamespace(id=9),
        db=db,
    )

    assert received == {"deal_journey_id": 22, "actor_id": "9", "expected_version": 7}
    assert opportunity.deal_journey_id == 22
    assert result.deal_journey_id == 22
    assert result.version == 8
    assert db.committed is True


@pytest.mark.asyncio
async def test_update_opportunity_deal_journey_maps_stale_version_to_conflict(monkeypatch) -> None:
    opportunity = _opportunity()
    db = _FakeDb()
    monkeypatch.setattr(opportunities_api, "_ensure_opportunity_not_pending", lambda db, opportunity, team_id: None)

    from app.services import deal_journey_service as deal_journey_module

    def fake_associate(db, db_opportunity, **kwargs):
        raise deal_journey_module.OpportunityDealJourneyConflictError(
            opportunity_id=301, expected_version=7, current_version=8
        )

    monkeypatch.setattr(deal_journey_module.deal_journey_service, "associate_opportunity", fake_associate)

    with pytest.raises(opportunities_api.HTTPException) as exc_info:
        await opportunities_api.update_opportunity_deal_journey(
            "opp_301",
            opportunities_api.OpportunityDealJourneyUpdate(deal_journey_id=22, expected_version=7),
            db_opportunity=opportunity,
            current_user=SimpleNamespace(id=9),
            db=db,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "OPPORTUNITY_VERSION_CONFLICT"
    assert exc_info.value.detail["details"]["current_version"] == 8
    assert db.rolled_back is True
