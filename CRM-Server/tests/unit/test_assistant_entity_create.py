"""CRM-165: the assistant creates CRM records only from a submitted form, once, with a receipt."""
# ruff: noqa: RUF001 -- Chinese user-facing copy uses native punctuation.

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import BigInteger, create_engine, event
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.assistant import AssistantAction, AssistantTask, AssistantTaskStatus
from app.models.assistant_conversation import AssistantConversation, AssistantConversationEntry
from app.models.assistant_crm_effect import AssistantCRMEffect
from app.models.assistant_turn import AssistantRequest, AssistantTurn, AssistantTurnEvent
from app.models.customer import Contact, Customer, CustomerMember, CustomerProduct
from app.models.team import Team, UserTeam
from app.models.user import User
from app.services.assistant import entity_tasks, turns
from app.services.assistant.coordinator import AssistantCoordinator
from app.services.assistant.entity_tasks import EntityExtraction
from app.services.assistant.task_state import load_waiting
from app.services.assistant.turns import AssistantStateConflict


@compiles(BigInteger, "sqlite")
def _bigint_as_int(element, compiler, **kwargs):
    return "INTEGER"


class NoChooser:
    async def choose(self, task):
        raise AssertionError("entity tasks never choose an activity kind")


@pytest.fixture
def db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'assistant-entity.db'}")

    @event.listens_for(engine, "before_cursor_execute", retval=True)
    def skip_indexes(conn, cursor, statement, parameters, context, executemany):
        return ("SELECT 1", ()) if statement.startswith("CREATE INDEX") else (statement, parameters)

    Base.metadata.create_all(engine, tables=[
        Customer.__table__, CustomerMember.__table__, CustomerProduct.__table__, Contact.__table__,
        AssistantCRMEffect.__table__,
        AssistantTask.__table__, AssistantConversation.__table__, AssistantConversationEntry.__table__,
        AssistantAction.__table__, AssistantRequest.__table__, AssistantTurn.__table__,
        AssistantTurnEvent.__table__, User.__table__, Team.__table__, UserTeam.__table__,
    ])
    permissions = [SimpleNamespace(code="customer:edit:own")]
    monkeypatch.setattr(
        "app.crud.permission.permission_crud.get_user_permissions", lambda *args: permissions,
    )
    monkeypatch.setattr(
        "app.services.customer_business_object_intelligence_service."
        "customer_business_object_intelligence_service.enqueue_object_change_refresh_after_commit",
        lambda **kwargs: None,
    )
    monkeypatch.setattr("app.api.assistant._coordinator", AssistantCoordinator(NoChooser()))
    monkeypatch.setattr(turns.DurableProgressReporter, "_record", lambda self, payload: None)
    monkeypatch.setattr(turns, "schedule_turn", lambda *args, **kwargs: None)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    session.add_all([
        User(id=2, name="虚构销售", email="entity-create@example.invalid"),
        Team(id=1, name="隔离验收团队", code="ENT001", owner_id=2),
        UserTeam(user_id=2, team_id=1),
        Customer(team_id=1, account_name="睿狐科技", public_id="cus_ruihu", city="上海", creator_id="2",
                 owner_id="2"),
        Customer(team_id=1, account_name="别家科技", public_id="cus_other", city="上海", creator_id="9",
                 owner_id="9"),
    ])
    session.commit()
    try:
        yield session, factory, permissions
    finally:
        session.close()
        engine.dispose()


SOURCE = "睿狐科技新增联系人王敏，采购经理，手机 138 0013 8000"


def _extraction(customer: str = "睿狐科技") -> EntityExtraction:
    return EntityExtraction.model_validate({
        "customer_name": {"value": customer, "quote": customer},
        "fields": [
            {"key": "name", "value": "王敏", "quote": "王敏"},
            {"key": "position", "value": "采购经理", "quote": "采购经理"},
            {"key": "mobile", "value": "13800138000", "quote": "138 0013 8000"},
            {"key": "email", "value": "wangmin@ruihu.example", "quote": "not in the text"},
        ],
    })


async def _start(
    db, monkeypatch, extraction: EntityExtraction, *, source: str = SOURCE, kind: str = "contact_create",
    key: str = "entity-create",
) -> AssistantTask:
    session, factory, _ = db

    async def extract(*args):
        return extraction

    monkeypatch.setattr(entity_tasks, "extract_entity", extract)
    task = turns.accept_create(session, team_id=1, user_id=2, key=key, goal=source, task_kind=kind)
    turn, accepted = turns.accept_submit(
        session, task=task, key=f"{key}-text", input_data={"kind": "text", "text": source, "choice": None},
        action_id=None, expected_version=None,
    )
    assert accepted
    await turns.execute_turn(turn.id, factory=factory)
    session.expire_all()
    session.refresh(task)
    return task


async def _submit(db, task: AssistantTask, key: str, input_data: dict[str, object]) -> None:
    session, factory, _ = db
    waiting = load_waiting(task)
    assert waiting is not None
    turn, accepted = turns.accept_submit(
        session, task=task, key=key, input_data={"text": None, "choice": None, **input_data},
        action_id=waiting.action_id, expected_version=waiting.expected_version,
    )
    assert accepted
    await turns.execute_turn(turn.id, factory=factory)
    session.expire_all()
    session.refresh(task)


async def _save(db, task: AssistantTask, key: str = "entity-save", **overrides: object) -> None:
    """Save the form as shown, plus the required gender the user picks (the text never says it)."""
    waiting = load_waiting(task)
    values = {field["key"]: field["default_value"] for field in waiting.form_fields} | {"gender": "2", **overrides}
    await _submit(db, task, key, {"kind": "submit_form", "values": values, "form_revision": waiting.form_revision})


def _form(task: AssistantTask) -> dict[str, dict[str, object]]:
    waiting = load_waiting(task)
    assert waiting is not None and waiting.type == "ENTITY_FORM"
    return {field["key"]: field for field in waiting.form_fields}


def _claims(session) -> list[str]:
    rows = session.query(AssistantAction).filter_by(action="proposal_command_claim").order_by(AssistantAction.id)
    return [row.result_json["status"] for row in rows]


@pytest.mark.asyncio
async def test_text_only_prefills_a_form_from_quoted_facts_and_writes_nothing(db, monkeypatch):
    session, _, _ = db
    task = await _start(db, monkeypatch, _extraction())

    form = _form(task)
    assert task.status == AssistantTaskStatus.ACTIVE
    assert load_waiting(task).field == "entity:contact_create"
    assert form["name"]["default_value"] == "王敏" and form["name"]["source_label"]
    assert form["mobile"]["default_value"] == "13800138000"
    assert not form["email"]["default_value"], "a value without a quote in the user's text must not be prefilled"
    assert form["email"].get("source_label") is None
    assert session.query(Contact).count() == 0
    assert session.query(AssistantCRMEffect).count() == 0


@pytest.mark.asyncio
async def test_submitted_form_writes_one_contact_with_effect_claim_and_receipt(db, monkeypatch):
    session, _, _ = db
    task = await _start(db, monkeypatch, _extraction())

    await _save(db, task, position="采购总监")

    contact = session.query(Contact).one()
    assert (contact.name, contact.position, contact.mobile, contact.team_id) == ("王敏", "采购总监", "13800138000", 1)
    effect = session.query(AssistantCRMEffect).one()
    assert effect.target_public_id == f"contact:{contact.id}"
    assert _claims(session) == ["SUCCEEDED"]
    assert task.status == AssistantTaskStatus.COMPLETED
    assert load_waiting(task) is None
    receipt = task.committed_json[-1]
    assert receipt["kind"] == "contact_create" and receipt["customer_public_id"] == "cus_ruihu"
    waited = session.query(AssistantTurnEvent).order_by(AssistantTurnEvent.id.desc()).first()
    assert waited.data_json["entity_receipt"]["public_id"] == f"contact:{contact.id}"


@pytest.mark.asyncio
async def test_invalid_submission_keeps_the_form_open_with_field_error(db, monkeypatch):
    session, _, _ = db
    task = await _start(db, monkeypatch, _extraction())

    await _save(db, task, mobile="12345")

    form = _form(task)
    assert form["mobile"]["error_message"] == "请填写 11 位手机号"
    assert form["mobile"]["default_value"] == "12345"
    assert form["position"]["default_value"] == "采购经理", "what the user typed survives the rejection"
    assert session.query(Contact).count() == 0
    assert _claims(session) == []


@pytest.mark.asyncio
async def test_existing_mobile_is_reported_not_duplicated(db, monkeypatch):
    session, _, _ = db
    customer = session.query(Customer).filter_by(public_id="cus_ruihu").one()
    session.add(Contact(team_id=1, customer_id=customer.id, name="王敏（旧）", mobile="13800138000", is_primary=0))
    session.commit()
    existing = session.query(Contact).one()
    task = await _start(db, monkeypatch, _extraction())

    await _save(db, task)

    assert session.query(Contact).count() == 1
    assert session.query(AssistantCRMEffect).count() == 0
    assert _claims(session) == ["NO_EFFECT"]
    assert task.status == AssistantTaskStatus.COMPLETED
    receipt = task.committed_json[-1]
    assert (receipt["outcome"], receipt["public_id"]) == ("existing", f"contact:{existing.id}")


@pytest.mark.asyncio
async def test_permission_revoked_before_submit_refuses_without_writing(db, monkeypatch):
    session, _, permissions = db
    task = await _start(db, monkeypatch, _extraction())
    permissions.clear()

    await _save(db, task)

    assert task.status == AssistantTaskStatus.FAILED
    assert task.last_error_code == "PERMISSION_DENIED"
    assert session.query(Contact).count() == 0
    assert _claims(session) == []


@pytest.mark.asyncio
async def test_customer_the_user_cannot_access_reads_as_not_found_and_offers_create(db, monkeypatch):
    session, _, _ = db
    task = await _start(db, monkeypatch, _extraction("别家科技"), source=SOURCE.replace("睿狐", "别家"))

    waiting = load_waiting(task)
    assert (waiting.type, waiting.field) == ("OBJECT_SELECTION", "customer")
    assert [item["id"] for item in waiting.candidates] == [entity_tasks.NEW_CUSTOMER]
    assert "cus_other" not in str(task.draft_json), "a denied match is never revealed or bound"
    assert session.query(Contact).count() == 0


@pytest.mark.asyncio
async def test_failed_write_without_effect_keeps_the_form_and_can_be_resubmitted(db, monkeypatch):
    session, _, _ = db
    task = await _start(db, monkeypatch, _extraction())
    from app.crud.customer import contact_crud

    real_create = contact_crud.create

    def broken(*args, **kwargs):
        raise OperationalError("INSERT", {}, Exception("db down"))

    monkeypatch.setattr(contact_crud, "create", broken)
    await _save(db, task)

    assert task.status == AssistantTaskStatus.ACTIVE
    assert load_waiting(task).hint.startswith("没有保存")
    assert _form(task)["name"]["default_value"] == "王敏"
    assert _claims(session) == ["NO_EFFECT"]
    assert session.query(Contact).count() == 0

    monkeypatch.setattr(contact_crud, "create", real_create)
    await _save(db, task, key="entity-save-again")

    assert session.query(Contact).count() == 1
    assert _claims(session) == ["NO_EFFECT", "SUCCEEDED"]
    assert task.status == AssistantTaskStatus.COMPLETED


@pytest.mark.asyncio
async def test_unprovable_write_result_fences_cancel_until_reconciled(db, monkeypatch):
    session, _, _ = db
    task = await _start(db, monkeypatch, _extraction())

    def broken(*args, **kwargs):
        raise OperationalError("INSERT", {}, Exception("connection lost mid-write"))

    def lookup_failed(*args, **kwargs):
        raise OperationalError("SELECT", {}, Exception("connection lost"))

    monkeypatch.setattr(entity_tasks, "record_effect", broken)
    monkeypatch.setattr(entity_tasks, "checked_effect", lookup_failed)
    await _save(db, task)

    assert _claims(session) == ["UNKNOWN"]
    assert session.query(Contact).count() == 0
    with pytest.raises(AssistantStateConflict, match="待核对"):
        entity_tasks.cancel_entity_task(session, task)


OPPORTUNITY_SOURCE = "给睿狐科技建个商机，200 个账号，3 年"


@pytest.fixture
def opportunity_catalog(db, monkeypatch):
    """A live catalog and a stand-in for the CRM create-with-approval transaction."""

    from app.models.opportunity import Opportunity, OpportunityProductModule
    from app.models.procurement import ProcurementMethod, ProcurementStageTemplate
    from app.models.product import Product, ProductModule
    from app.services.assistant.crm_effects import AssistantCRMNoEffect, record_effect

    session, _, permissions = db
    Base.metadata.create_all(session.bind, tables=[
        Product.__table__, ProductModule.__table__, ProcurementMethod.__table__, ProcurementStageTemplate.__table__,
        Opportunity.__table__, OpportunityProductModule.__table__,
    ])
    session.add_all([
        ProcurementMethod(id=11, team_id=1, code="P11", name="直采", sort_order=1, created_by="2"),
        ProcurementStageTemplate(id=21, team_id=1, procurement_method_id=11, template_code="S21", stage_name="初步接触",
                                 win_probability=10, sort_order=1, is_default_start=1, created_by="2"),
        Product(id=1, public_id="prd_1", team_id=1, code="P1", name="Apifox", created_by="2", is_active=True),
        ProductModule(id=1, public_id="prm_1", team_id=1, product_id=1, code="M1", name="基础版", created_by="2",
                      sort_order=1, is_active=True),
    ])
    session.query(Customer).filter_by(public_id="cus_ruihu").update({"default_procurement_method_id": 11})
    session.commit()
    permissions.append(SimpleNamespace(code="opportunity:create"))
    created: list[dict[str, object]] = []
    approval = {"flow": True}

    async def create_opportunity(opportunity, *, team_id, current_user, db, assistant_command):
        if not approval["flow"]:
            raise AssistantCRMNoEffect("请先配置审批流程")
        created.append(opportunity.model_dump(mode="json"))
        record_effect(db, assistant_command, "opportunity_create", target_public_id="opp_new", approval_id=42)
        db.commit()
        return SimpleNamespace(public_id="opp_new")

    monkeypatch.setattr("app.api.opportunities.create_opportunity", create_opportunity)
    return created, approval


def _customer_only() -> EntityExtraction:
    return EntityExtraction.model_validate({"customer_name": {"value": "睿狐科技", "quote": "睿狐科技"}, "fields": []})


async def _start_opportunity(db, monkeypatch) -> AssistantTask:
    return await _start(db, monkeypatch, _customer_only(), source=OPPORTUNITY_SOURCE, kind="opportunity_create")


async def _save_opportunity(db, task: AssistantTask, key: str = "opp-save", **overrides: object) -> None:
    waiting = load_waiting(task)
    values = {field["key"]: field["default_value"] for field in waiting.form_fields}
    values |= {"total_amount": 600000, "expected_closing_date": "2027-03-31", **overrides}
    await _submit(db, task, key, {"kind": "submit_form", "values": values, "form_revision": waiting.form_revision})


@pytest.mark.asyncio
async def test_opportunity_form_prefills_from_text_and_submits_for_approval(db, monkeypatch, opportunity_catalog):
    session, _, _ = db
    created, _ = opportunity_catalog
    task = await _start_opportunity(db, monkeypatch)

    form = _form(task)
    assert (form["user_count"]["default_value"], form["subscription_years"]["default_value"]) == (200, 3)
    assert not created

    await _save_opportunity(db, task)

    assert len(created) == 1 and created[0]["customer_id"] == "cus_ruihu" and created[0]["user_count"] == 200
    assert _claims(session) == ["SUCCEEDED"]
    assert task.status == AssistantTaskStatus.COMPLETED
    receipt = task.committed_json[-1]
    assert (receipt["kind"], receipt["public_id"], receipt["approval_phase"]) == (
        "opportunity_create", "opp_new", "pending_review")
    waited = session.query(AssistantTurnEvent).order_by(AssistantTurnEvent.id.desc()).first()
    assert waited.data_json["entity_receipt"]["approval_phase"] == "pending_review"
    assert "proposal_receipt" not in waited.data_json
    assert waited.data_json["message"].startswith("商机已创建，待审批")


@pytest.mark.asyncio
async def test_missing_approval_flow_is_relayed_and_the_form_stays_open(db, monkeypatch, opportunity_catalog):
    session, _, _ = db
    created, approval = opportunity_catalog
    approval["flow"] = False
    task = await _start_opportunity(db, monkeypatch)

    await _save_opportunity(db, task)

    assert task.status == AssistantTaskStatus.ACTIVE
    assert _form(task)["user_count"]["default_value"] == 200
    assert load_waiting(task).form_fields and _claims(session) == ["NO_EFFECT"]
    waited = session.query(AssistantTurnEvent).order_by(AssistantTurnEvent.id.desc()).first()
    assert waited.data_json["message"] == "请先配置审批流程"
    assert session.query(AssistantCRMEffect).count() == 0

    approval["flow"] = True
    await _save_opportunity(db, task, key="opp-save-again")

    assert _claims(session) == ["NO_EFFECT", "SUCCEEDED"] and len(created) == 1


@pytest.mark.asyncio
async def test_indistinguishable_opportunity_is_never_created_twice(db, monkeypatch, opportunity_catalog):
    session, _, _ = db
    created, _ = opportunity_catalog
    monkeypatch.setattr(
        "app.services.assistant.opportunity_target_matching.match_opportunity_target",
        lambda *args, **kwargs: SimpleNamespace(status="AMBIGUOUS"),
    )
    task = await _start_opportunity(db, monkeypatch)

    await _save_opportunity(db, task)

    assert not created and _claims(session) == ["NO_EFFECT"]
    assert task.status == AssistantTaskStatus.ACTIVE
    waited = session.query(AssistantTurnEvent).order_by(AssistantTurnEvent.id.desc()).first()
    assert waited.data_json["message"].startswith("已存在相同或无法区分的商机")


# ---------------------------------------------------------------------------
# D18 typed supplements, D20 待补充
# ---------------------------------------------------------------------------


async def _say(db, monkeypatch, task: AssistantTask, text: str, extraction: EntityExtraction, key: str) -> None:
    async def extract(*args):
        return extraction

    monkeypatch.setattr(entity_tasks, "extract_entity", extract)
    await _submit(db, task, key, {"kind": "text", "text": text})


@pytest.mark.asyncio
async def test_typed_supplement_fills_empty_fields_overrides_named_ones_and_never_writes(db, monkeypatch):
    session, _, _ = db
    task = await _start(db, monkeypatch, _extraction())
    said = "她叫王敏敏，职位是采购总监，邮箱 wm@ruihu.example"

    await _say(db, monkeypatch, task, said, EntityExtraction.model_validate({"fields": [
        {"key": "name", "value": "王敏敏", "quote": "王敏敏"},
        {"key": "position", "value": "采购总监", "quote": "采购总监"},
        {"key": "email", "value": "wm@ruihu.example", "quote": "wm@ruihu.example"},
    ]}), "entity-supplement")

    form = _form(task)
    assert (form["email"]["default_value"], form["email"]["source_label"]) == ("wm@ruihu.example", "刚补充")
    assert (form["position"]["default_value"], form["position"]["source_label"]) == ("采购总监", "刚补充")
    assert form["name"]["default_value"] == "王敏", "an unnamed filled field keeps its value"
    assert form["mobile"]["default_value"] == "13800138000"
    assert session.query(Contact).count() == 0 and _claims(session) == []


@pytest.mark.asyncio
async def test_deferred_draft_is_listed_and_resumes_with_its_values(db, monkeypatch):
    session, _, _ = db
    task = await _start(db, monkeypatch, _extraction())

    await _submit(db, task, "entity-defer", {
        "kind": "submit_form", "choice": "defer", "form_revision": load_waiting(task).form_revision,
    })

    assert (task.status, load_waiting(task).type) == (AssistantTaskStatus.ACTIVE, "ENTITY_DEFERRED")
    drafts = entity_tasks.pending_drafts(session, team_id=1, user_id=2)
    assert [(d.public_id, d.label, d.customer_name) for d in drafts] == [(task.public_id, "联系人", "睿狐科技")]
    assert entity_tasks.pending_drafts(session, team_id=1, user_id=9) == []

    await _submit(db, task, "entity-resume", {"kind": "submit_field", "choice": "resume"})

    form = _form(task)
    assert form["name"]["default_value"] == "王敏" and form["position"]["default_value"] == "采购经理"
    assert session.query(Contact).count() == 0


@pytest.mark.asyncio
async def test_defer_phrase_parks_the_form_and_resume_rechecks_permission(db, monkeypatch):
    session, _, permissions = db
    task = await _start(db, monkeypatch, _extraction())

    await _submit(db, task, "entity-defer-text", {"kind": "text", "text": "手机号稍后再补"})
    assert load_waiting(task).type == "ENTITY_DEFERRED"
    permissions.clear()

    await _submit(db, task, "entity-resume", {"kind": "submit_field", "choice": "resume"})

    assert task.status == AssistantTaskStatus.FAILED
    assert session.query(Contact).count() == 0


@pytest.mark.asyncio
async def test_supplement_never_fills_two_parked_drafts_at_once(db, monkeypatch):
    from app.services.assistant.conversation import ConversationService
    from tests.unit.test_assistant_conversation import Classifier, decision, text

    session, _, _ = db
    drafts = [
        await _start(db, monkeypatch, _extraction(), key="entity-create-a"),
        await _start(db, monkeypatch, _extraction(), key="entity-create-b"),
    ]
    for index, task in enumerate(drafts):
        await _submit(db, task, f"entity-defer-{index}", {"kind": "text", "text": "先放着"})
    service = ConversationService(classifier=Classifier(decision(speech="PROVIDE_SUPPLEMENT", obj="CONTACT")))
    initial = service.open(session, team_id=1, user_id=2)

    response = await service.submit_text(
        session, team_id=1, user_id=2, request=text(initial.version, "睿狐科技那个联系人邮箱是 wm@ruihu.example"),
    )

    assert response.submission is None
    assert "要补到哪一份" in response.conversation.messages[-1].text
    for task in drafts:
        session.refresh(task)
        assert load_waiting(task).type == "ENTITY_DEFERRED"
    assert session.query(Contact).count() == 0


@pytest.mark.asyncio
async def test_supplement_in_conversation_resumes_the_only_parked_draft(db, monkeypatch):
    from app.services.assistant.conversation import ConversationService
    from tests.unit.test_assistant_conversation import Classifier, decision, text

    session, _, _ = db
    task = await _start(db, monkeypatch, _extraction())
    await _submit(db, task, "entity-defer", {"kind": "text", "text": "先放着"})
    service = ConversationService(classifier=Classifier(decision(speech="PROVIDE_SUPPLEMENT", obj="CONTACT")))
    initial = service.open(session, team_id=1, user_id=2)

    response = await service.submit_text(
        session, team_id=1, user_id=2, request=text(initial.version, "睿狐科技那个联系人邮箱是 wm@ruihu.example"),
    )

    assert response.submission is not None and response.submission.task_public_id == task.public_id
    assert session.query(AssistantTask).count() == 1


# ---------------------------------------------------------------------------
# D29 跟进后资料
# ---------------------------------------------------------------------------

MEETING = "今天和睿狐科技开会，新对接人王敏，采购经理，手机 138 0013 8000；开票抬头用睿狐科技有限公司"


def _committed_activity(session) -> AssistantTask:
    from app.services.assistant.contracts import DraftField, TaskDraft

    draft = TaskDraft(source_segments=[MEETING], content=DraftField(status="ACCEPTED", value=MEETING))
    task = AssistantTask(
        team_id=1, user_id=2, status=AssistantTaskStatus.ACTIVE, goal=MEETING,
        draft_json=draft.model_dump(mode="json"),
        authority_json={"customer_public_id": "cus_ruihu"},
        committed_json=[{"kind": "customer_activity", "public_id": "act_1", "customer_public_id": "cus_ruihu"}],
    )
    session.add(task)
    session.commit()
    return task


@pytest.fixture
def profile_items(monkeypatch):
    """The model names the invoice title first; the list must follow the rep's own order."""

    from app.services.assistant import profile_proposals
    from app.services.assistant.profile_proposals import ProfileExtraction

    async def extract(*args):
        return ProfileExtraction.model_validate({"items": [
            {"kind": "invoice_title_create", "summary": "开票抬头：睿狐科技有限公司",
             "quote": "开票抬头用睿狐科技有限公司",
             "fields": [{"key": "title", "value": "睿狐科技有限公司", "quote": "睿狐科技有限公司"}]},
            {"kind": "contact_create", "summary": "新联系人王敏", "quote": "新对接人王敏，采购经理，手机 138 0013 8000",
             "fields": [{"key": "name", "value": "王敏", "quote": "王敏"},
                        {"key": "mobile", "value": "13800138000", "quote": "138 0013 8000"}]},
            {"kind": "contact_create", "summary": "编造的联系人", "quote": "原文没有这句"},
        ]})

    async def next_proposal(db, task, *, reporter=None):
        return task, "没有其他建议", True

    monkeypatch.setattr(profile_proposals, "extract_profile_items", extract)
    monkeypatch.setattr("app.services.assistant.proposals.offer_next_proposal", next_proposal)


async def _answer(session, task: AssistantTask, user_input: dict[str, object]):
    from app.services.assistant.coordinator import AssistantInput

    outcome = await AssistantCoordinator(NoChooser()).handle_task(session, task, AssistantInput(**user_input))
    session.commit()
    session.refresh(task)
    return outcome


@pytest.mark.asyncio
async def test_profile_items_follow_the_activity_and_each_opens_its_own_child(db, profile_items):
    from app.services.assistant.presentation import task_view

    session, _, _ = db
    activity = _committed_activity(session)

    listed = await _answer(session, activity, {"kind": "continue_proposals"})

    assert listed.reply.card == "profile_proposals"
    rows = task_view(activity, session).profile_proposals
    assert [(row.kind, row.decision) for row in rows] == [
        ("contact_create", "pending"), ("invoice_title_create", "pending"),
    ], "utterance order, and the made-up quote is dropped"

    await _answer(session, activity, {"kind": "submit_field", "choice": "go:0"})

    child = session.query(AssistantTask).filter_by(task_kind="contact_create").one()
    assert child.parent_task_id == activity.id
    assert _form(child)["name"]["default_value"] == "王敏"
    assert load_waiting(activity).type == "PROFILE_PROPOSALS", "the other row is still open"
    row = task_view(activity, session).profile_proposals[0]
    assert (row.child_task_public_id, row.child_waiting_type) == (child.public_id, "ENTITY_FORM")

    finished = await _answer(session, activity, {"kind": "submit_field", "choice": "skip:1"})

    assert finished.reply.message.endswith("没有其他建议"), "the opportunity proposals follow the list"
    assert session.query(Contact).count() == 0, "去补充 opens a form; it never writes"


@pytest.mark.asyncio
async def test_a_refused_profile_item_never_affects_the_others_or_the_activity(db, profile_items):
    from app.services.assistant.presentation import task_view

    session, _, _ = db
    activity = _committed_activity(session)
    await _answer(session, activity, {"kind": "continue_proposals"})

    await _answer(session, activity, {"kind": "submit_field", "choice": "go:1"})  # no invoice-title permission
    await _answer(session, activity, {"kind": "submit_field", "choice": "go:0"})

    rows = task_view(activity, session).profile_proposals
    assert [row.child_status for row in rows] == ["ACTIVE", "FAILED"]
    assert activity.status == AssistantTaskStatus.ACTIVE
    assert activity.committed_json[0]["public_id"] == "act_1"


@pytest.mark.asyncio
async def test_a_cancelled_activity_lists_no_profile_items(db, profile_items):
    session, _, _ = db
    activity = _committed_activity(session)
    activity.committed_json = []
    session.commit()

    outcome = await _answer(session, activity, {"kind": "cancel"})

    assert outcome.reply.message.endswith("资料可以直接让我单独保存")
    assert session.query(AssistantTask).count() == 1
