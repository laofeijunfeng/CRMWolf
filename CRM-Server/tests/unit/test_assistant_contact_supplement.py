"""CRM-176: existing-contact matching, Entry A profile dedupe/supplement, Entry B direct supplement, and guardrails."""
# ruff: noqa: RUF001, RUF003 -- Chinese user-facing copy uses native punctuation.

from __future__ import annotations

import pytest

from app.models.assistant import AssistantTask, AssistantTaskStatus
from app.models.assistant_crm_effect import AssistantCRMEffect
from app.models.customer import Contact
from app.services.assistant import profile_proposals
from app.services.assistant.contact_matching import (
    ContactSignals,
    compute_contact_delta,
    match_existing_contact,
    merge_contact_remark,
)
from app.services.assistant.contracts import EntityCreateReceipt
from app.services.assistant.conversation import ConversationService
from app.services.assistant.entity_tasks import EntityExtraction
from app.services.assistant.presentation import task_view
from app.services.assistant.profile_proposals import ProfileExtraction
from app.services.assistant.task_state import load_waiting
from tests.unit.test_assistant_conversation import (
    Classifier,
    db as conv_db,  # noqa: F401 -- pytest fixture
    decision,
    text,
)
from tests.unit.test_assistant_entity_create import (
    _answer,
    _claims,
    _committed_activity,
    _form,
    _project,
    _start,
    _submit,
    db,  # noqa: F401 -- pytest fixture
)


def _add_contact(
    session,
    *,
    customer_id: int = 1,
    name: str = "孙自豪",
    mobile: str = "13800138000",
    position: str = "技术总监",
    gender: str = "1",
    wechat_id: str | None = None,
    email: str | None = None,
    reports_to: int | None = None,
    remark: str | None = "偏好线下沟通",
) -> Contact:
    contact = Contact(
        team_id=1,
        customer_id=customer_id,
        name=name,
        gender=gender,
        position=position,
        mobile=mobile,
        wechat_id=wechat_id,
        email=email,
        reports_to=reports_to,
        remark=remark,
    )
    session.add(contact)
    session.commit()
    session.refresh(contact)
    return contact


def _supplement_extraction(
    *,
    customer: str = "睿狐科技",
    fields: list[dict[str, str]],
) -> EntityExtraction:
    return EntityExtraction.model_validate({
        "customer_name": {"value": customer, "quote": customer},
        "fields": fields,
    })


# ---------------------------------------------------------------------------
# AC3: Deterministic matching & nickname non-merge
# ---------------------------------------------------------------------------


def test_matching_rules_mobile_exact_name_ambiguous_conflict_and_nickname(db):  # noqa: F811
    session, _, _ = db
    c1 = _add_contact(session, name="孙自豪", mobile="13800138000", position="技术总监")
    c2 = _add_contact(session, name="王敏", mobile="13900139000", position="采购经理")

    # Strong match by mobile even when name differs slightly
    m_mobile = match_existing_contact([c1, c2], ContactSignals(name="孙总", mobiles=("138 0013 8000",)))
    assert m_mobile.status == "MATCHED" and m_mobile.contact is not None and m_mobile.contact.id == c1.id

    # Exact name match with no mobile
    m_name = match_existing_contact([c1, c2], ContactSignals(name="孙自豪"))
    assert m_name.status == "MATCHED" and m_name.contact is not None and m_name.contact.id == c1.id

    # Nickname / short name must NEVER auto-merge
    m_nick = match_existing_contact([c1, c2], ContactSignals(name="孙总"))
    assert m_nick.status == "NO_MATCH" and m_nick.contact is None

    # Exact name match with different mobile -> MOBILE_CONFLICT
    m_conflict = match_existing_contact([c1, c2], ContactSignals(name="孙自豪", mobiles=("13700137000",)))
    assert m_conflict.status == "MOBILE_CONFLICT"
    assert m_conflict.contact is not None and m_conflict.contact.id == c1.id
    assert m_conflict.conflict_mobile == "13700137000"

    # Duplicate names under same customer -> AMBIGUOUS_NAME
    c3 = _add_contact(session, name="孙自豪", mobile="13600136000", position="架构师")
    m_ambig = match_existing_contact([c1, c2, c3], ContactSignals(name="孙自豪"))
    assert m_ambig.status == "AMBIGUOUS_NAME"
    assert {c.id for c in m_ambig.candidates} == {c1.id, c3.id}


def test_merge_contact_remark_appends_without_duplicating_existing_lines():
    assert merge_contact_remark("偏好线下沟通", "下周三技术评审") == ("偏好线下沟通\n下周三技术评审", True)
    assert merge_contact_remark("偏好线下沟通\n下周三技术评审", "下周三技术评审") == ("偏好线下沟通\n下周三技术评审", False)
    assert merge_contact_remark(None, "首次沟通顺利") == ("首次沟通顺利", True)


def test_compute_contact_delta_only_fills_blank_fields_and_ignores_existing(db):  # noqa: F811
    session, _, _ = db
    boss = _add_contact(session, name="李总", mobile="13500135000", position="VP")
    target = _add_contact(
        session,
        name="孙自豪",
        mobile="13800138000",
        wechat_id="sun_existing",
        email=None,
        reports_to=None,
        remark="偏好线下沟通",
    )
    delta = compute_contact_delta(
        target,
        ContactSignals(
            name="孙自豪",
            wechat_id="sun_new_should_ignore",
            email="sun@ruihu.example",
            reports_to_name="李总",
            remarks=("偏好线下沟通",),
        ),
        contacts=[boss, target],
    )
    assert delta.has_delta is True
    assert delta.wechat_id is None, "non-blank wechat_id must not be overwritten"
    assert delta.email == "sun@ruihu.example"
    assert delta.reports_to_id == boss.id
    assert delta.remark_append is None, "duplicate remark must not produce delta"


# ---------------------------------------------------------------------------
# AC1 & AC2: Entry A (profile_proposals) noise filtering & incremental proposal
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_entry_a_silently_filters_existing_contact_without_delta(db, monkeypatch):  # noqa: F811
    session, _, _ = db
    _add_contact(
        session,
        name="孙自豪",
        mobile="13800138000",
        wechat_id="sun_wx",
        email="sun@ruihu.example",
        remark="偏好线下沟通",
    )
    activity = _committed_activity(session)
    activity.goal = "今天和睿狐科技的孙自豪碰了面，偏好线下沟通"
    activity.draft_json = {**(activity.draft_json or {}), "source_segments": ["今天和睿狐科技的孙自豪碰了面，偏好线下沟通"]}
    session.commit()
    async def extract(*args):
        return ProfileExtraction.model_validate({
            "items": [{
                "kind": "contact_create",
                "summary": "联系人孙自豪",
                "quote": "孙自豪碰了面，偏好线下沟通",
                "fields": [
                    {"key": "name", "value": "孙自豪", "quote": "孙自豪"},
                    {"key": "remark", "value": "偏好线下沟通", "quote": "偏好线下沟通"},
                ],
            }]
        })

    async def next_proposal(db_sess, task, *, reporter=None):
        return task, "没有其他建议", True

    monkeypatch.setattr(profile_proposals, "extract_profile_items", extract)
    monkeypatch.setattr("app.services.assistant.proposals.offer_next_proposal", next_proposal)

    outcome = await _answer(session, activity, {"kind": "continue_proposals"})

    assert outcome.reply.card != "profile_proposals"
    assert outcome.reply.message.endswith("没有其他建议")
    assert not task_view(activity, session).profile_proposals
    assert session.query(AssistantTask).count() == 1


@pytest.mark.asyncio
async def test_entry_a_proposes_contact_supplement_and_opens_readonly_remark_form(db, monkeypatch):  # noqa: F811
    session, _, _ = db
    target = _add_contact(
        session,
        name="孙自豪",
        mobile="13800138000",
        wechat_id="sun_existing",
        email=None,
        remark="偏好线下沟通",
    )
    activity = _committed_activity(session)
    activity.goal = "和睿狐科技的孙自豪聊完，邮箱 sun@ruihu.example，关注私有化部署报价"
    activity.draft_json = {**(activity.draft_json or {}), "source_segments": ["和睿狐科技的孙自豪聊完，邮箱 sun@ruihu.example，关注私有化部署报价"]}
    session.commit()
    async def extract(*args):
        return ProfileExtraction.model_validate({
            "items": [{
                "kind": "contact_create",
                "summary": "联系人孙自豪",
                "quote": "孙自豪聊完，邮箱 sun@ruihu.example，关注私有化部署报价",
                "fields": [
                    {"key": "name", "value": "孙自豪", "quote": "孙自豪"},
                    {"key": "email", "value": "sun@ruihu.example", "quote": "sun@ruihu.example"},
                    {"key": "remark", "value": "关注私有化部署报价", "quote": "关注私有化部署报价"},
                ],
            }]
        })

    async def next_proposal(db_sess, task, *, reporter=None):
        return task, "没有其他建议", True

    monkeypatch.setattr(profile_proposals, "extract_profile_items", extract)
    monkeypatch.setattr("app.services.assistant.proposals.offer_next_proposal", next_proposal)

    listed = await _answer(session, activity, {"kind": "continue_proposals"})
    assert listed.reply.card == "profile_proposals"
    rows = task_view(activity, session).profile_proposals
    assert len(rows) == 1
    assert rows[0].kind == "contact_supplement"
    assert rows[0].label == "更新已有联系人"
    assert "补充 孙自豪" in rows[0].summary
    assert rows[0].extracted_summary is not None
    assert "邮箱 sun@ruihu.example" in rows[0].extracted_summary

    # Verify PROFILE_PROPOSALS UI projection shows deduplicated group title and 打开补充表单 button
    from app.services.assistant.ui_projection import _profile_row_state

    projected_proposals = _project(session, activity, profile_proposals.PROMPT)
    proposal_interaction = next(b for b in projected_proposals.blocks if b.type == "interaction")
    assert proposal_interaction.hint == profile_proposals.HINT
    go_opt = next(opt for opt in proposal_interaction.options if opt.value == "go:0")
    assert go_opt.label == "打开补充表单"
    assert go_opt.group == "更新已有联系人：孙自豪（新备注、邮箱）"
    assert "已识别：" in (go_opt.description or "") and "｜原话：" in (go_opt.description or "")

    # User clicks "打开补充表单" -> opens contact_supplement form without required create fields
    await _answer(session, activity, {"kind": "submit_field", "choice": "go:0"})
    child = session.query(AssistantTask).filter_by(task_kind="contact_supplement").one()
    form = _form(child)
    assert set(form.keys()) == {"existing_remark", "remark_append", "email"}
    assert form["existing_remark"]["read_only"] is True
    assert form["existing_remark"]["default_value"] == "偏好线下沟通"
    assert form["remark_append"]["default_value"] == "关注私有化部署报价"
    assert form["email"]["default_value"] == "sun@ruihu.example"
    assert "wechat_id" not in form, "already non-blank wechat_id is hidden"
    assert "mobile" not in form and "gender" not in form and "position" not in form

    # Verify UI projection preserves read_only on existing_remark and sets supplement_contact action
    projected = _project(session, child, "请确认补充内容")
    interaction = next(b for b in projected.blocks if b.type == "interaction")
    assert interaction.business_action == "supplement_contact"
    projected_fields = {f.key: f for f in interaction.fields}
    assert projected_fields["existing_remark"].read_only is True
    assert projected_fields["remark_append"].read_only is False
    # Wire payload omits read_only when False
    dumped = interaction.model_dump(mode="json")
    dumped_fields = {f["key"]: f for f in dumped["fields"]}
    assert dumped_fields["existing_remark"]["read_only"] is True
    assert "read_only" not in dumped_fields["remark_append"]

    # Submit the supplement form
    waiting = load_waiting(child)
    await _submit(
        db,
        child,
        "supplement-save-1",
        {
            "kind": "submit_form",
            "values": {
                "remark_append": "关注私有化部署报价",
                "email": "sun@ruihu.example",
            },
            "form_revision": waiting.form_revision,
        },
    )
    session.refresh(target)
    assert target.remark == "偏好线下沟通\n关注私有化部署报价"
    assert target.email == "sun@ruihu.example"
    assert target.wechat_id == "sun_existing"
    assert child.status == AssistantTaskStatus.COMPLETED
    receipt = EntityCreateReceipt.model_validate(child.committed_json[-1])
    assert receipt.kind == "contact_supplement"
    assert receipt.outcome == "supplemented"
    assert receipt.public_id == f"contact:{target.id}"
    settled_row = task_view(activity, session).profile_proposals[0]
    assert _profile_row_state(settled_row) == "已更新"

# ---------------------------------------------------------------------------
# AC3: Ambiguous name disambiguation & mobile conflict protection + fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_entry_b_ambiguous_name_selects_contact_or_falls_back_to_create(db, monkeypatch):  # noqa: F811
    session, _, _ = db
    c1 = _add_contact(session, name="孙自豪", mobile="13800138000", position="技术总监", remark="原备注A")
    c2 = _add_contact(session, name="孙自豪", mobile="13600136000", position="架构师", remark="原备注B")

    source = "给睿狐科技的孙自豪加一条备注：下周评审"
    extraction = _supplement_extraction(
        fields=[
            {"key": "name", "value": "孙自豪", "quote": "孙自豪"},
            {"key": "remark", "value": "下周评审", "quote": "下周评审"},
        ],
    )
    task = await _start(db, monkeypatch, extraction, source=source, kind="contact_supplement", key="ambig-1")

    waiting = load_waiting(task)
    assert (waiting.type, waiting.field) == ("OBJECT_SELECTION", "contact_select")
    candidate_ids = [c["id"] for c in waiting.candidates]
    assert str(c1.id) in candidate_ids
    assert str(c2.id) in candidate_ids
    assert "create_new_contact" in candidate_ids

    projected = _project(session, task, waiting.prompt)
    interaction = next(b for b in projected.blocks if b.type == "interaction")
    assert interaction.business_action == "select_contact"

    # Choose the second contact -> opens supplement form for c2
    await _submit(db, task, "ambig-pick-c2", {"kind": "submit_field", "choice": str(c2.id)})
    form = _form(task)
    assert form["existing_remark"]["default_value"] == "原备注B"
    assert form["remark_append"]["default_value"] == "下周评审"

    # Start another task and choose "create_new_contact" -> switches to contact_create
    task2 = await _start(db, monkeypatch, extraction, source=source, kind="contact_supplement", key="ambig-2")
    await _submit(db, task2, "ambig-pick-create", {"kind": "submit_field", "choice": "create_new_contact"})
    assert task2.task_kind == "contact_create"
    waiting2 = load_waiting(task2)
    assert waiting2.field == "entity:contact_create"
    assert "mobile" in _form(task2)


@pytest.mark.asyncio
async def test_entry_b_mobile_conflict_requires_confirmation_and_never_overwrites_mobile(db, monkeypatch):  # noqa: F811
    session, _, _ = db
    target = _add_contact(session, name="孙自豪", mobile="13800138000", position="技术总监", remark="原备注")

    source = "给睿狐科技的孙自豪（13900139000）补一条备注：预算已批"
    extraction = _supplement_extraction(
        fields=[
            {"key": "name", "value": "孙自豪", "quote": "孙自豪"},
            {"key": "mobile", "value": "13900139000", "quote": "13900139000"},
            {"key": "remark", "value": "预算已批", "quote": "预算已批"},
        ],
    )
    task = await _start(db, monkeypatch, extraction, source=source, kind="contact_supplement", key="conflict-1")

    waiting = load_waiting(task)
    assert (waiting.type, waiting.field) == ("OBJECT_SELECTION", "contact_mobile_conflict")
    assert [c["id"] for c in waiting.candidates] == ["keep_existing_contact", "create_new_contact"]

    projected = _project(session, task, waiting.prompt)
    interaction = next(b for b in projected.blocks if b.type == "interaction")
    assert interaction.business_action == "resolve_contact_conflict"

    # Keep existing contact -> opens supplement form with new mobile noted in remark_append
    await _submit(db, task, "conflict-keep", {"kind": "submit_field", "choice": "keep_existing_contact"})
    form = _form(task)
    assert "13900139000" in str(form["remark_append"]["default_value"])
    assert "预算已批" in str(form["remark_append"]["default_value"])

    waiting = load_waiting(task)
    await _submit(
        db,
        task,
        "conflict-save",
        {
            "kind": "submit_form",
            "values": {"remark_append": form["remark_append"]["default_value"]},
            "form_revision": waiting.form_revision,
        },
    )
    session.refresh(target)
    assert target.mobile == "13800138000", "existing mobile must never be overwritten"
    assert "原备注" in (target.remark or "")
    assert "新提手机号：13900139000" in (target.remark or "")


# ---------------------------------------------------------------------------
# AC5: Direct routing for CONTACT + TRANSITION
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_routing_contact_transition_opens_contact_supplement_while_others_refuse(conv_db):  # noqa: F811
    service = ConversationService(
        classifier=Classifier(decision(speech="REQUEST_ACTION", obj="CONTACT", operation="TRANSITION"))
    )
    initial = service.open(conv_db, team_id=1, user_id=2)
    response = await service.submit_text(
        conv_db,
        team_id=1,
        user_id=2,
        request=text(initial.version, "给瑞众人寿的孙自豪加一条备注：下周三技术评审"),
    )

    assert response.submission is not None
    tasks = conv_db.query(AssistantTask).all()
    assert [t.task_kind for t in tasks] == ["contact_supplement"]


# ---------------------------------------------------------------------------
# AC4 & AC6: Idempotency, permission refusal, and optimistic concurrency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_duplicate_remark_submit_is_idempotent_and_returns_existing(db, monkeypatch):  # noqa: F811
    session, _, _ = db
    target = _add_contact(session, name="孙自豪", mobile="13800138000", remark="偏好线下沟通\n下周三技术评审")

    source = "给睿狐科技的孙自豪加一条备注：下周三技术评审"
    extraction = _supplement_extraction(
        fields=[
            {"key": "name", "value": "孙自豪", "quote": "孙自豪"},
            {"key": "remark", "value": "下周三技术评审", "quote": "下周三技术评审"},
        ],
    )
    task = await _start(db, monkeypatch, extraction, source=source, kind="contact_supplement", key="idem-1")
    waiting = load_waiting(task)
    await _submit(
        db,
        task,
        "idem-save",
        {
            "kind": "submit_form",
            "values": {"remark_append": "下周三技术评审"},
            "form_revision": waiting.form_revision,
        },
    )
    session.refresh(target)
    assert target.remark == "偏好线下沟通\n下周三技术评审"
    receipt = EntityCreateReceipt.model_validate(task.committed_json[-1])
    assert receipt.outcome == "existing"
    assert _claims(session) == ["SUCCEEDED"]
    assert session.query(AssistantCRMEffect).count() == 1


@pytest.mark.asyncio
async def test_permission_refusal_blocks_supplement_and_writes_nothing(db, monkeypatch):  # noqa: F811
    session, _, permissions = db
    target = _add_contact(session, name="孙自豪", mobile="13800138000", remark="原备注")

    source = "给睿狐科技的孙自豪加一条备注：无权写入"
    extraction = _supplement_extraction(
        fields=[
            {"key": "name", "value": "孙自豪", "quote": "孙自豪"},
            {"key": "remark", "value": "无权写入", "quote": "无权写入"},
        ],
    )
    task = await _start(db, monkeypatch, extraction, source=source, kind="contact_supplement", key="perm-1")
    waiting = load_waiting(task)
    permissions.clear()

    await _submit(
        db,
        task,
        "perm-save",
        {
            "kind": "submit_form",
            "values": {"remark_append": "无权写入"},
            "form_revision": waiting.form_revision,
        },
    )

    assert task.status == AssistantTaskStatus.FAILED
    assert task.last_error_code == "PERMISSION_DENIED"
    assert load_waiting(task) is None
    assert _claims(session) == []
    session.refresh(target)
    assert target.remark == "原备注"


@pytest.mark.asyncio
async def test_concurrent_contact_edit_triggers_conflict_and_preserves_history(db, monkeypatch):  # noqa: F811
    session, _, _ = db
    target = _add_contact(session, name="孙自豪", mobile="13800138000", remark="原备注1", email=None)

    source = "给睿狐科技的孙自豪加一条备注：新备注2，邮箱 sun@ruihu.example"
    extraction = _supplement_extraction(
        fields=[
            {"key": "name", "value": "孙自豪", "quote": "孙自豪"},
            {"key": "remark", "value": "新备注2", "quote": "新备注2"},
            {"key": "email", "value": "sun@ruihu.example", "quote": "sun@ruihu.example"},
        ],
    )
    task = await _start(db, monkeypatch, extraction, source=source, kind="contact_supplement", key="conc-1")
    waiting = load_waiting(task)
    assert waiting.type == "ENTITY_FORM"

    # Simulate another user editing the contact concurrently (bumping revision + remark + email)
    target.remark = "原备注1\n同事补充的并发备注"
    target.email = "concurrent@ruihu.example"
    target.post_commit_revision = int(target.post_commit_revision or 1) + 1
    session.commit()

    # First submit detects revision conflict, refreshes existing_remark, and re-issues form
    await _submit(
        db,
        task,
        "conc-save-1",
        {
            "kind": "submit_form",
            "values": {"remark_append": "新备注2", "email": "sun@ruihu.example"},
            "form_revision": waiting.form_revision,
        },
    )
    assert task.status == AssistantTaskStatus.ACTIVE
    reissued = _form(task)
    assert reissued["existing_remark"]["default_value"] == "原备注1\n同事补充的并发备注"
    assert "未覆盖" in str(reissued["email"].get("error_message") or "")

    # Simulate another concurrent remark-only bump before second submit -> triggers revision conflict error on remark_append
    target.remark = "原备注1\n同事补充的并发备注\n同事第二次补充"
    target.post_commit_revision = int(target.post_commit_revision or 1) + 1
    session.commit()

    waiting2 = load_waiting(task)
    await _submit(
        db,
        task,
        "conc-save-2",
        {
            "kind": "submit_form",
            "values": {"remark_append": "新备注2"},
            "form_revision": waiting2.form_revision,
        },
    )
    assert task.status == AssistantTaskStatus.ACTIVE
    reissued2 = _form(task)
    assert reissued2["existing_remark"]["default_value"] == "原备注1\n同事补充的并发备注\n同事第二次补充"
    assert "已被他人更新" in str(reissued2["remark_append"].get("error_message") or "")

    # Final submit succeeds and preserves all historical remarks + concurrent email
    waiting3 = load_waiting(task)
    await _submit(
        db,
        task,
        "conc-save-3",
        {
            "kind": "submit_form",
            "values": {"remark_append": "新备注2"},
            "form_revision": waiting3.form_revision,
        },
    )
    session.refresh(target)
    assert target.remark == "原备注1\n同事补充的并发备注\n同事第二次补充\n新备注2"
    assert target.email == "concurrent@ruihu.example", "concurrently filled email must not be overwritten"
    assert task.status == AssistantTaskStatus.COMPLETED
