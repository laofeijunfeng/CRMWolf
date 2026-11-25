"""CRM-162: owner-transfer Feishu notifications (queueing rules and card rendering)."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from app.models.outbound_notification_job import OutboundNotificationEventType
from app.services import owner_transfer_notification as notifier
from app.services.feishu_notification import FeishuNotificationService

OPERATOR = 1
MEMBERS = {1, 2, 3}


class _Db:
    def __init__(self):
        self.rollbacks = 0

    def rollback(self):
        self.rollbacks += 1


@pytest.fixture
def queued(monkeypatch):
    calls = []
    monkeypatch.setattr(notifier.team_crud, "is_member", lambda db, team_id, user_id: user_id in MEMBERS)
    monkeypatch.setattr(notifier.user_crud, "get_by_id", lambda db, user_id: SimpleNamespace(name=f"user{user_id}"))
    monkeypatch.setattr(
        notifier.outbound_notification_job_service, "queue_committed", lambda db, **kwargs: calls.append(kwargs)
    )
    monkeypatch.setattr(notifier.lead_follow_up_crud, "get_latest_for_team", lambda db, **kwargs: None)
    monkeypatch.setattr(notifier.contact_crud, "get_card_contact", lambda db, **kwargs: None)
    monkeypatch.setattr(notifier.customer_activity_crud, "get_latest_by_customer_id", lambda db, **kwargs: None)
    return calls


def _lead():
    return SimpleNamespace(id=7, lead_name="线索A", contact_name="王五", contact_phone="13800000000")


def _customer():
    return SimpleNamespace(id=9, public_id="cus_9", account_name="客户A")


def _assign_lead(db, *, previous, new, operator=OPERATOR):
    notifier.queue_lead_assignment_notifications(
        db, team_id=1, lead=_lead(), previous_owner_id=previous, new_owner_id=new,
        operator_id=operator, operator_name="管理员",
    )


def _transfer_customer(db, *, previous="3", new="2", scope="all", key=None):
    notifier.queue_customer_transfer_notifications(
        db, team_id=1, customer=_customer(), previous_owner_id=previous, new_owner_id=new,
        transfer_scope=scope, transferred_opportunities=2, transferred_contracts=1, locked_contracts=1,
        remark="工作交接", operator_id=OPERATOR, operator_name="管理员", idempotency_key=key,
    )


def test_pool_lead_notifies_only_new_owner(queued):
    _assign_lead(_Db(), previous=None, new="2")

    assert [c["event_type"] for c in queued] == [OutboundNotificationEventType.LEAD_ASSIGNED]
    assert queued[0]["recipient_user_ids"] == [2]
    assert queued[0]["payload_json"]["previous_owner_name"] is None
    assert "remark" not in queued[0]["payload_json"]


def test_reassigned_lead_notifies_both_owners(queued):
    _assign_lead(_Db(), previous="3", new="2")

    assert [(c["event_type"], c["recipient_user_ids"]) for c in queued] == [
        (OutboundNotificationEventType.LEAD_ASSIGNED, [2]),
        (OutboundNotificationEventType.LEAD_ASSIGNED_PREVIOUS, [3]),
    ]
    assert queued[0]["payload_json"]["previous_owner_name"] == "user3"
    assert queued[1]["payload_json"]["new_owner_name"] == "user2"


@pytest.mark.parametrize(
    ("previous", "new", "expected"),
    [
        ("1", "2", [[2]]),  # operator was the previous owner
        ("3", "1", [[3]]),  # operator assigned to themself
        ("99", "2", [[2]]),  # previous owner left the team
        ("2", "2", [[2]]),  # owner unchanged: no previous-owner card
    ],
)
def test_recipients_are_team_members_other_than_operator(queued, previous, new, expected):
    _assign_lead(_Db(), previous=previous, new=new)

    assert [c["recipient_user_ids"] for c in queued] == expected


def test_customer_transfer_snapshots_card_content(queued, monkeypatch):
    monkeypatch.setattr(
        notifier.contact_crud, "get_card_contact",
        lambda db, **kwargs: SimpleNamespace(name="李四", mobile="13900000000"),
    )
    monkeypatch.setattr(
        notifier.customer_activity_crud, "get_latest_by_customer_id",
        lambda db, **kwargs: SimpleNamespace(
            activity_kind="ONLINE_MEETING", occurred_at=datetime(2026, 11, 20, 14, 30),
            summary="记" * 150, source_content=None,
        ),
    )

    _transfer_customer(_Db(), key="1:customer_transferred:op")

    received, previous = queued
    payload = received["payload_json"]
    assert payload["contact_name"] == "李四"
    assert payload["follow_up"]["kind_label"] == "会议纪要"
    assert payload["follow_up"]["occurred_at"] == "2026-11-20 14:30"
    assert payload["follow_up"]["content"] == "记" * 100 + "…"
    assert payload["remark"] == "工作交接"
    assert payload["cascade"] == {"opportunities": 2, "contracts": 1, "locked": 1}
    assert payload["detail_path"] == "/customers?customerId=cus_9"
    assert received["idempotency_key"] == "1:customer_transferred:op"
    assert previous["idempotency_key"] == "1:customer_transferred:op:previous"
    assert previous["payload_json"]["cascade"] == payload["cascade"]


def test_customer_cascade_omitted_when_scope_moves_nothing(queued):
    _transfer_customer(_Db(), scope="none")

    assert all(c["payload_json"]["cascade"] is None for c in queued)


def test_queue_failure_is_swallowed_and_rolled_back(queued, monkeypatch):
    def boom(db, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(notifier.outbound_notification_job_service, "queue_committed", boom)
    db = _Db()

    _transfer_customer(db)
    _assign_lead(db, previous="3", new="2")

    assert db.rollbacks == 2


@pytest.fixture
def feishu(monkeypatch):
    service = FeishuNotificationService()
    sent = []
    bound = {2}

    async def send_to_user(db, team_id, user_id, msg_type, content):
        if user_id not in bound:
            return False
        sent.append(content)
        return True

    monkeypatch.setattr(service, "send_to_user", send_to_user)
    monkeypatch.setattr(service, "_absolute_frontend_url", lambda db, team_id, path: f"https://crm{path}")
    return service, sent


def _lines(card):
    return [e["text"]["content"] for e in card["elements"] if e["tag"] == "div"]


@pytest.mark.asyncio
async def test_received_card_omits_empty_optional_fields(feishu):
    service, sent = feishu

    result = await service.notify_owner_transfer_received(
        None, 1, [2, 3], entity_type="LEAD", name="线索A", operator_name=None, previous_owner_name=None,
        contact_name=None, contact_phone="13800000000", follow_up=None, remark=None, cascade=None,
        detail_path="/leads",
    )

    assert result == {"success": 1, "failed": 0, "skipped": 1}  # user 3 has no Feishu binding
    (card,) = sent
    assert card["header"]["title"]["content"] == "🎯 你收到一条新分配的线索"
    assert _lines(card) == [
        "**线索名称**\uff1a线索A",
        "**原负责人**\uff1a无",
        "**联系人**\uff1a暂无联系人",
    ]
    assert card["elements"][-1]["actions"][0]["url"] == "https://crm/leads"


@pytest.mark.asyncio
async def test_customer_cards_render_follow_up_remark_and_cascade(feishu):
    service, sent = feishu
    cascade = {"opportunities": 2, "contracts": 1, "locked": 1}

    await service.notify_owner_transfer_received(
        None, 1, [2], entity_type="CUSTOMER", name="客户A", operator_name="管理员", previous_owner_name="张三",
        contact_name="李四", contact_phone="13900000000",
        follow_up={
            "kind_label": "跟进记录", "occurred_at": "2026-11-20 14:30", "method": "电话", "content": "约了下周演示",
        },
        remark="工作交接", cascade=cascade, detail_path="/customers?customerId=cus_9",
    )
    await service.notify_owner_transfer_previous(
        None, 1, [2], entity_type="CUSTOMER", name="客户A", new_owner_name="赵六", operator_name="管理员",
        cascade=cascade,
    )

    received, previous = sent
    cascade_line = "**随客户转移**\uff1a商机 2 个、合同 1 份\uff1b未转移合同 1 份\uff08审批中或已签署\uff09"
    assert _lines(received) == [
        "**客户名称**\uff1a客户A",
        "**操作人**\uff1a管理员",
        "**原负责人**\uff1a张三",
        "**联系人**\uff1a李四",
        "**联系电话**\uff1a13900000000",
        "**最近跟进记录**\uff1a2026-11-20 14:30 · 电话\n约了下周演示",
        "**移交备注**\uff1a工作交接",
        cascade_line,
    ]
    assert previous["header"]["title"]["content"] == "📤 你负责的客户已移交"
    assert _lines(previous) == [
        "**客户名称**\uff1a客户A",
        "**移交给**\uff1a赵六",
        "**操作人**\uff1a管理员",
        cascade_line,
    ]
    assert all(e["tag"] == "div" for e in previous["elements"])  # no button
