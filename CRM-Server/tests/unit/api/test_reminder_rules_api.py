"""Reminder rule API: team isolation, rule validation, and enablement."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import reminder_rules as reminder_rules_api
from app.core import database, deps
from app.core.database import Base
from app.models.reminder_rule import ReminderRule
from app.models.reminder_rule_run import ReminderRuleRun
from app.models.role import Role
from app.models.team import Team, UserTeam
from app.models.user import User, UserStatus


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


def _rule() -> dict:
    return {
        "name": "商机阶段停留提醒",
        "object_type": "opportunity",
        "trigger": "schedule",
        "status": "FOLLOWING",
        "inactive_days": 7,
        "require_no_new_activity": True,
        "recipients": ["owner", "user:8"],
        "message_template": "{商机名称} 在{当前阶段}已停留 {天数} 天，期间没有新的客户活动。",  # noqa: RUF001
        "channels": ["in_app", "feishu"],
    }


@pytest.fixture()
def api_env(monkeypatch):
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(
        engine,
        tables=[
            User.__table__,
            Team.__table__,
            UserTeam.__table__,
            Role.__table__,
            ReminderRule.__table__,
            ReminderRuleRun.__table__,
        ],
    )
    session = sessionmaker(bind=engine)()
    current_user = User(id=1, email="admin@example.com", name="管理员", status=UserStatus.ACTIVE)
    session.add(current_user)
    session.add(Team(id=101, name="团队A", code="TEAM_A", owner_id=1))
    session.add(Team(id=202, name="团队B", code="TEAM_B", owner_id=1))
    session.commit()

    permissions = {"automation:read", "automation:create", "automation:edit", "automation:publish"}
    monkeypatch.setattr(
        "app.core.deps.permission_crud.get_user_permissions",
        lambda _db, user_id, team_id=None: [SimpleNamespace(code=code) for code in permissions],
    )
    app = FastAPI()
    app.include_router(reminder_rules_api.router)
    team_state = {"id": 101}

    def _get_db():
        yield session

    app.dependency_overrides[deps.get_db] = _get_db
    app.dependency_overrides[database.get_db] = _get_db
    app.dependency_overrides[deps.get_current_user_team] = lambda: team_state["id"]
    app.dependency_overrides[deps.get_current_active_user] = lambda: current_user
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, team_state=team_state, db=session, permissions=permissions)
    session.close()
    engine.dispose()


def test_create_enabled_rule_requires_create_and_publish(api_env):
    api_env.permissions.discard("automation:publish")
    assert api_env.client.post("/v1/reminder-rules", json=_rule()).status_code == 403
    api_env.permissions.add("automation:publish")
    assert api_env.client.post("/v1/reminder-rules", json=_rule()).status_code == 201
    api_env.permissions.discard("automation:create")
    assert api_env.client.post("/v1/reminder-rules", json=_rule()).status_code == 403


def test_recipient_picker_lists_only_active_current_team_users(api_env):
    api_env.db.add_all([
        User(id=8, email="same@example.com", name="本团队成员", status=UserStatus.ACTIVE),
        User(id=9, email="inactive@example.com", name="停用成员", status=UserStatus.INACTIVE),
        User(id=10, email="other@example.com", name="其他团队成员", status=UserStatus.ACTIVE),
        UserTeam(user_id=1, team_id=101),
        UserTeam(user_id=8, team_id=101),
        UserTeam(user_id=9, team_id=101),
        UserTeam(user_id=10, team_id=202),
    ])
    api_env.db.commit()
    response = api_env.client.get("/v1/reminder-rules/recipients")
    assert response.status_code == 200
    assert response.json() == [{"id": "1", "name": "管理员"}, {"id": "8", "name": "本团队成员"}]
    api_env.permissions.discard("automation:read")
    assert api_env.client.get("/v1/reminder-rules/recipients").status_code == 403


def test_create_lists_only_the_current_team(api_env):
    created = api_env.client.post("/v1/reminder-rules", json=_rule())
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["enabled"] is True
    assert body["sentence"] == "当跟进中的商机进入当前阶段满 7 天，且期间没有新的客户活动，通知负责人和指定成员。"  # noqa: RUF001

    api_env.team_state["id"] = 202
    listed = api_env.client.get("/v1/reminder-rules")
    assert listed.status_code == 200
    assert listed.json() == []


def test_invalid_rule_is_rejected_before_save(api_env):
    payload = _rule()
    payload["recipients"] = ["submitter"]
    response = api_env.client.post("/v1/reminder-rules", json=payload)
    assert response.status_code == 422
    assert api_env.client.get("/v1/reminder-rules").json() == []


def test_disable_keeps_the_rule_but_stops_it(api_env):
    created = api_env.client.post("/v1/reminder-rules", json=_rule()).json()
    updated = api_env.client.put(
        f"/v1/reminder-rules/{created['id']}/enabled",
        json={"enabled": False, "expected_revision": created["revision"]},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["enabled"] is False
    assert api_env.client.get("/v1/reminder-rules").json()[0]["enabled"] is False

def _v2_editable_rule() -> dict:
    return {
        **_rule(),
        "version": 2,
        "status": None,
        "inactive_days": None,
        "recipients": ["owner"],
        "trigger_time": "09:30",
        "conditions": [{"field": "status", "operator": "in", "value": ["FOLLOWING"]}],
        "channels": ["feishu"],
        "message_title": "商机提醒",
    }


def test_edit_v2_rule_keeps_its_identity_and_disabled_state(api_env):
    created = api_env.client.post("/v1/reminder-rules", json=_v2_editable_rule()).json()
    rule_id = created["id"]
    disabled = api_env.client.put(
        f"/v1/reminder-rules/{rule_id}/enabled",
        json={"enabled": False, "expected_revision": created["revision"]},
    )
    assert disabled.status_code == 200
    api_env.permissions.discard("automation:create")
    api_env.permissions.discard("automation:publish")
    updated_payload = {
        **_v2_editable_rule(),
        "name": "修改后的提醒",
        "trigger_time": "16:30",
        "message_template": "新的提醒内容",
        "expected_revision": disabled.json()["revision"],
    }
    response = api_env.client.put(f"/v1/reminder-rules/{rule_id}", json=updated_payload)
    assert response.status_code == 200, response.text
    assert response.json()["enabled"] is False
    assert response.json()["id"] == rule_id
    assert response.json()["trigger_time"] == "16:30"
    assert "每日 16:30" in response.json()["sentence"]
    listed = api_env.client.get("/v1/reminder-rules").json()
    assert [(rule["id"], rule["name"], rule["message_template"], rule["enabled"]) for rule in listed] == [
        (rule_id, "修改后的提醒", "新的提醒内容", False)
    ]


def test_edit_rule_enforces_team_permission_and_validation_without_overwriting(api_env):
    created = api_env.client.post("/v1/reminder-rules", json=_v2_editable_rule()).json()
    rule_id = created["id"]
    url = f"/v1/reminder-rules/{rule_id}"
    change = {**_v2_editable_rule(), "name": "更新的规则", "expected_revision": created["revision"]}
    api_env.team_state["id"] = 202
    assert api_env.client.put(url, json=change).status_code == 404
    api_env.team_state["id"] = 101
    api_env.permissions.discard("automation:edit")
    assert api_env.client.put(url, json=change).status_code == 403
    api_env.permissions.add("automation:edit")
    invalid = {**change, "conditions": [{"field": "status", "operator": "in", "value": []}]}
    assert api_env.client.put(url, json=invalid).status_code == 422
    assert api_env.client.get("/v1/reminder-rules").json()[0]["name"] == created["name"]


def test_edit_does_not_silently_convert_legacy_rules(api_env):
    legacy = api_env.client.post("/v1/reminder-rules", json=_rule()).json()
    response = api_env.client.put(
        f"/v1/reminder-rules/{legacy['id']}",
        json={**_v2_editable_rule(), "expected_revision": legacy["revision"]},
    )
    assert response.status_code == 422
    assert api_env.client.get("/v1/reminder-rules").json()[0]["version"] == 1


def test_edit_rejects_stale_rule_without_overwriting_newer_changes(api_env):
    created = api_env.client.post("/v1/reminder-rules", json=_v2_editable_rule()).json()
    url = f"/v1/reminder-rules/{created['id']}"
    first = api_env.client.put(
        url,
        json={**_v2_editable_rule(), "name": "第一位编辑者", "expected_revision": created["revision"]},
    )
    assert first.status_code == 200, first.text
    stale = api_env.client.put(
        url,
        json={**_v2_editable_rule(), "name": "过期的编辑", "expected_revision": created["revision"]},
    )
    assert stale.status_code == 409, stale.text
    assert api_env.client.get("/v1/reminder-rules").json()[0]["name"] == "第一位编辑者"

def test_edit_rejects_stale_revision_when_timestamp_does_not_change(api_env):
    created = api_env.client.post("/v1/reminder-rules", json=_v2_editable_rule()).json()
    url = f"/v1/reminder-rules/{created['id']}"
    assert created["revision"] == 1
    first = api_env.client.put(
        url,
        json={**_v2_editable_rule(), "name": "第一位编辑者", "expected_revision": created["revision"]},
    )
    assert first.status_code == 200, first.text
    assert first.json()["revision"] == 2

    # MySQL's original DATETIME column stores only seconds. Mimic two edits
    # landing within one second, so their public timestamps cannot distinguish them.
    api_env.db.query(ReminderRule).filter(ReminderRule.id == created["id"]).update(
        {
            ReminderRule.last_modified_time: datetime.fromisoformat(created["last_modified_time"]),
            ReminderRule.revision: first.json()["revision"],
        },
        synchronize_session=False,
    )
    api_env.db.commit()
    stale = api_env.client.put(
        url,
        json={**_v2_editable_rule(), "name": "过期草稿", "expected_revision": created["revision"]},
    )
    assert stale.status_code == 409, stale.text
    assert api_env.client.get("/v1/reminder-rules").json()[0]["name"] == "第一位编辑者"


def test_edit_detects_intervening_publish_without_changing_enabled_state(api_env):
    created = api_env.client.post("/v1/reminder-rules", json=_v2_editable_rule()).json()
    updated = api_env.client.put(
        f"/v1/reminder-rules/{created['id']}/enabled",
        json={"enabled": False, "expected_revision": created["revision"]},
    )
    assert updated.status_code == 200
    assert updated.json()["revision"] == created["revision"] + 1
    stale = api_env.client.put(
        f"/v1/reminder-rules/{created['id']}",
        json={**_v2_editable_rule(), "expected_revision": created["revision"]},
    )
    assert stale.status_code == 409, stale.text
    assert api_env.client.get("/v1/reminder-rules").json()[0]["enabled"] is False

def test_stale_publish_request_cannot_overwrite_newer_toggle(api_env):
    created = api_env.client.post("/v1/reminder-rules", json=_v2_editable_rule()).json()
    url = f"/v1/reminder-rules/{created['id']}/enabled"
    first = api_env.client.put(url, json={"enabled": False, "expected_revision": created["revision"]})
    assert first.status_code == 200, first.text
    assert first.json()["revision"] == created["revision"] + 1
    stale = api_env.client.put(url, json={"enabled": True, "expected_revision": created["revision"]})
    assert stale.status_code == 409, stale.text
    assert api_env.client.get("/v1/reminder-rules").json()[0]["enabled"] is False


def test_edit_rejects_revision_changed_during_validation(api_env, monkeypatch):
    created = api_env.client.post("/v1/reminder-rules", json=_v2_editable_rule()).json()
    original_validate = reminder_rules_api._ensure_valid

    def concurrent_change(payload, db, team_id):
        original_validate(payload, db, team_id)
        saved = db.get(ReminderRule, created["id"])
        saved.rule = {**saved.rule, "name": "另一位编辑者"}
        db.commit()

    monkeypatch.setattr(reminder_rules_api, "_ensure_valid", concurrent_change)
    response = api_env.client.put(
        f"/v1/reminder-rules/{created['id']}",
        json={**_v2_editable_rule(), "name": "过期草稿", "expected_revision": created["revision"]},
    )
    assert response.status_code == 409, response.text
    assert api_env.client.get("/v1/reminder-rules").json()[0]["name"] == "另一位编辑者"


def test_run_history_lists_sent_reminders_for_the_current_team(api_env):
    created = api_env.client.post("/v1/reminder-rules", json=_rule()).json()
    api_env.db.add(
        ReminderRuleRun(
            team_id=101,
            rule_id=created["id"],
            object_type="opportunity",
            object_id=11,
            window_key="stage:2026-09-15T09:30:00",
            recipient_ids="7,8",
            message="华东电力扩容 在报价已停留 8 天，期间没有新的客户活动。",  # noqa: RUF001
            sent_count=2,
        )
    )
    api_env.db.commit()
    listed = api_env.client.get("/v1/reminder-rules/runs")
    assert listed.status_code == 200, listed.text
    assert listed.json()[0]["message"].startswith("华东电力扩容")
    assert listed.json()[0]["sent_count"] == 2


def test_catalog_exposes_seven_objects_and_v2_rule_round_trips(api_env):
    response = api_env.client.get("/v1/reminder-rules/catalog")
    assert response.status_code == 200, response.text
    catalog = response.json()
    assert len(catalog) == 7
    assert (
        next(item for item in catalog if item["object_type"] == "customer")["fields"][0]["options"][-1]["value"]
        == "INACTIVE"
    )
    for object_spec in catalog:
        payload = {
            "version": 2,
            "name": "每日提醒",
            "object_type": object_spec["object_type"],
            "trigger": "schedule",
            "status": None,
            "inactive_days": None,
            "date_field": None,
            "offset_days": 0,
            "require_no_new_activity": False,
            "trigger_time": "09:30",
            "conditions": [
                {"field": "status", "operator": "in", "value": [object_spec["fields"][0]["options"][0]["value"]]}
            ],
            "recipients": [object_spec["recipients"][0]["value"]],
            "message_title": "提醒",
            "message_template": "消息",
            "channels": ["feishu"],
            "notify_once_per_window": True,
        }
        created = api_env.client.post("/v1/reminder-rules", json=payload)
        assert created.status_code == 201, created.text
        assert created.json()["version"] == 2
        assert created.json()["conditions"] == payload["conditions"]
    assert len(api_env.client.get("/v1/reminder-rules").json()) == 7


def test_v2_api_rejects_unsupported_operator_and_duplicate_fields(api_env):
    base = {
        **_rule(),
        "version": 2,
        "trigger_time": "09:30",
        "status": None,
        "inactive_days": None,
        "conditions": [{"field": "status", "operator": "in", "value": ["FOLLOWING"]}],
    }
    for conditions in (
        [
            {"field": "status", "operator": "in", "value": ["FOLLOWING"]},
            {"field": "status", "operator": "in", "value": ["WON"]},
        ],
        [{"field": "expected_closing_date", "operator": "not_empty", "value": True}],
    ):
        assert api_env.client.post("/v1/reminder-rules", json={**base, "conditions": conditions}).status_code == 422


def test_v2_saved_conditions_control_daily_delivery(api_env):
    import asyncio
    from datetime import datetime, timedelta

    from app.models.customer import Customer
    from app.services.reminder_rule_execution import execute_due_reminder_rules

    Customer.__table__.create(api_env.db.bind)
    now = datetime(2026, 9, 23, 9, 30)
    api_env.db.add(UserTeam(user_id=1, team_id=101))
    api_env.db.add(
        Customer(
            id=11,
            team_id=101,
            account_name="客户",
            city="上海",
            owner_id="1",
            creator_id="1",
            status=1,
            created_time=now - timedelta(days=3),
        )
    )
    api_env.db.commit()
    payload = {
        "version": 2,
        "name": "跟进客户创建三天",
        "object_type": "customer",
        "trigger": "schedule",
        "status": None,
        "inactive_days": None,
        "date_field": None,
        "offset_days": 0,
        "require_no_new_activity": False,
        "trigger_time": "09:30",
        "channels": ["feishu"],
        "conditions": [
            {"field": "created_time", "operator": "older_than_days", "value": 3},
            {"field": "status", "operator": "in", "value": ["FOLLOWING"]},
            {"field": "owner", "operator": "not_empty", "value": True},
        ],
        "recipients": ["owner"],
        "message_title": "客户提醒",
        "message_template": "{客户名称}需要跟进",
    }
    response = api_env.client.post("/v1/reminder-rules", json=payload)
    assert response.status_code == 201, response.text
    sent = []

    def deliver(team_id, user_ids, title, content):
        sent.append((team_id, user_ids, content))
        return {"sent": len(user_ids), "skipped": 0}

    def run(at):
        return asyncio.run(execute_due_reminder_rules(api_env.db, now=at, deliver=deliver)).sent_count

    assert run(now - timedelta(minutes=1)) == 0
    assert run(now) == 0  # status WON blocks the old-enough customer
    customer = api_env.db.query(Customer).one()
    customer.status = 0
    api_env.db.commit()
    assert run(now) == 1
    assert run(now + timedelta(days=1)) == 0
    assert sent == [(101, [1], "客户需要跟进")]


def test_api_rejects_rules_without_runtime_handlers(api_env):
    for object_type, trigger in (
        ("opportunity", "change"),
        ("opportunity", "date"),
        ("follow_up_task", "schedule"),
        ("payment_plan", "schedule"),
    ):
        payload = {**_rule(), "object_type": object_type, "trigger": trigger}
        if object_type == "follow_up_task":
            payload.update(status="OPEN", inactive_days=7, recipients=["owner"], message_template="任务提醒")
        if object_type == "payment_plan":
            payload.update(
                status="PENDING", inactive_days=7, recipients=["contract_owner"], message_template="回款提醒"
            )
        assert api_env.client.post("/v1/reminder-rules", json=payload).status_code == 422
    assert api_env.client.get("/v1/reminder-rules").json() == []


def test_v2_api_rejects_policy_runtime_cannot_honor(api_env):
    payload = {
        **_rule(),
        "version": 2,
        "status": None,
        "inactive_days": None,
        "trigger_time": "09:30",
        "conditions": [{"field": "status", "operator": "in", "value": ["FOLLOWING"]}],
        "channels": ["feishu"],
    }
    for invalid in ({"channels": ["in_app"]}, {"channels": ["feishu", "in_app"]}, {"notify_once_per_window": False}):
        assert api_env.client.post("/v1/reminder-rules", json={**payload, **invalid}).status_code == 422


def test_v2_api_rejects_explicit_users_outside_active_team(api_env):
    api_env.db.add(User(id=8, email="outsider@example.com", name="其他团队成员", status=UserStatus.ACTIVE))
    api_env.db.add(UserTeam(user_id=8, team_id=202))
    api_env.db.commit()
    payload = {
        **_rule(),
        "version": 2,
        "status": None,
        "inactive_days": None,
        "trigger_time": "09:30",
        "conditions": [{"field": "status", "operator": "in", "value": ["FOLLOWING"]}],
        "channels": ["feishu"],
        "recipients": ["user:8"],
        "message_template": "提醒",
    }
    assert api_env.client.post("/v1/reminder-rules", json=payload).status_code == 422
    api_env.db.add(UserTeam(user_id=8, team_id=101))
    api_env.db.commit()
    assert api_env.client.post("/v1/reminder-rules", json=payload).status_code == 201
    user = api_env.db.query(User).filter(User.id == 8).one()
    user.status = UserStatus.INACTIVE
    api_env.db.commit()
    assert api_env.client.post("/v1/reminder-rules", json=payload).status_code == 422
