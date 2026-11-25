"""Root routing for direct-create sentences: entity tasks, page links for unsupported writes, one intent question."""
# ruff: noqa: RUF001 -- Tests use the exact Chinese UI copy.

import pytest

from app.models.assistant import AssistantTask
from app.models.assistant_turn import AssistantTurn
from app.services.assistant.conversation import ConversationService
from app.services.assistant.task_state import load_waiting
from tests.unit.test_assistant_conversation import Classifier, db, decision, text  # noqa: F401 -- db is a fixture


@pytest.mark.parametrize(
    ("obj", "kind"),
    [
        ("CONTACT", "contact_create"),
        ("INVOICE_TITLE", "invoice_title_create"),
        ("DEPLOYMENT_INFO", "deployment_create"),
        ("CUSTOMER", "customer_create"),
        ("OPPORTUNITY", "opportunity_create"),
    ],
)
async def test_entity_create_opens_one_task_of_that_kind(db, obj, kind):  # noqa: F811
    service = ConversationService(classifier=Classifier(decision(speech="REQUEST_ACTION", obj=obj)))
    initial = service.open(db, team_id=1, user_id=2)
    response = await service.submit_text(db, team_id=1, user_id=2, request=text(initial.version, "帮我新建一下"))

    assert response.submission is not None
    tasks = db.query(AssistantTask).all()
    assert [task.task_kind for task in tasks] == [kind]
    assert response.submission.task_public_id == tasks[0].public_id
    assert db.query(AssistantTurn).count() == 1
    assert "只记录客户沟通" not in response.conversation.messages[-1].text


@pytest.mark.parametrize(
    ("obj", "operation", "page"),
    [
        ("LEAD", "CREATE", "leads"),
        ("PAYMENT_RECORD", "CREATE", "payments"),
        ("CONTRACT", "CREATE", "contracts"),
        ("INVOICE_TITLE", "TRANSITION", "invoices"),
        ("CONTACT", "DELETE", "customers"),
        ("CUSTOMER_MEMBER", "CREATE", "customers"),
    ],
)
async def test_unsupported_write_points_at_its_page_and_writes_nothing(db, obj, operation, page):  # noqa: F811
    service = ConversationService(
        classifier=Classifier(decision(speech="REQUEST_ACTION", obj=obj, operation=operation))
    )
    initial = service.open(db, team_id=1, user_id=2)
    response = await service.submit_text(db, team_id=1, user_id=2, request=text(initial.version))

    assert response.submission is None
    assert db.query(AssistantTask).count() == db.query(AssistantTurn).count() == 0
    reply = response.conversation.messages[-1]
    assert reply.text.endswith("这次没有写入。")
    assert [link.page for link in reply.links] == [page]


async def test_unsure_create_asks_entity_or_activity_once(db):  # noqa: F811
    unsure = decision(obj="CONTACT").model_copy(update={"confidence": 0.6})
    service = ConversationService(classifier=Classifier(unsure))
    initial = service.open(db, team_id=1, user_id=2)
    response = await service.submit_text(
        db, team_id=1, user_id=2, request=text(initial.version, "换了对接人，新的是陈涛")
    )

    assert response.submission is None
    task = db.query(AssistantTask).one()
    waiting = load_waiting(task)
    assert (waiting.type, waiting.field) == ("OBJECT_SELECTION", "intent")
    assert [c["id"] for c in waiting.candidates] == ["entity", "activity"]
    assert response.conversation.messages[-1].text == "这句要存为联系人，还是记一条跟进？"


async def test_unclear_sentence_lists_new_capabilities(db):  # noqa: F811
    unsure = decision().model_copy(update={"confidence": 0.3})
    service = ConversationService(classifier=Classifier(unsure))
    initial = service.open(db, team_id=1, user_id=2)
    response = await service.submit_text(db, team_id=1, user_id=2, request=text(initial.version))

    reply = response.conversation.messages[-1].text
    assert "新建联系人、开票抬头、部署信息、商机、客户" in reply
    assert reply.endswith("这次没有写入。")
    assert db.query(AssistantTask).count() == 0
