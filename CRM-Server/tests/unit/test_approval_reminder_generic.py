"""Task A8 fix：提醒催办任务泛化单元测试。

缺陷：app/tasks/approval_reminder.py 原先按 approval.contract_id 查合同，
泛化后回款/发票审批 contract_id=None → 查询永远 None → continue，
导致三级催办（轻/中/强）对 PAYMENT/INVOICE 永不触发。

覆盖：
- PAYMENT 审批（contract_id=None, business_type=PAYMENT）等待 25h → 轻度提醒触发，
  notify_approval_reminder 收到 entity_type=PAYMENT / entity_name / business_id
- INVOICE 审批等待 73h → 三级提醒全部触发，实体类型透传 INVOICE，
  notify_approval_timeout_alert（提交人+管理员）亦收到 entity_type=INVOICE
- ORPHAN（未知 business_type）→ get_adapter 抛 ValueError → 跳过，不发通知
- 业务单据被删（get_entity 返 None）→ 跳过，不发通知
- CONTRACT 审批回归：仍能正常催办，entity_type=CONTRACT
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.tasks.approval_reminder import ApprovalReminderScheduler
from app.constants.business_types import BusinessType


# ---------- helpers --------------------------------------------------------


def _make_approval(
    *,
    business_type: str,
    business_id: int,
    waiting_hours: float,
    submitter_id: str = "ou_submitter",
    team_id: int = 1,
) -> MagicMock:
    """构造内存 Approval 对象（不持久化）。"""
    approval = MagicMock()
    approval.id = 1
    approval.business_type = business_type
    approval.business_id = business_id
    approval.contract_id = None  # 泛化后回款/发票为 None
    approval.team_id = team_id
    approval.submitter_id = submitter_id
    approval.created_time = datetime.now() - timedelta(hours=waiting_hours)
    approval.status = "PENDING"

    node = MagicMock()
    node.id = 10
    node.node_name = "财务审批"
    node.approve_role = "APPROVER"
    approval.current_node = node
    return approval


def _make_user(*, open_id: str, name: str, uid: int = 1):
    u = MagicMock()
    u.id = uid
    u.feishu_open_id = open_id
    u.name = name
    return u


def _make_db(approvals, submitter=None):
    """构造 mock SessionLocal：query(Approval)→待审批列表，query(User)→提交人。"""
    db = MagicMock()

    q_approval = MagicMock()
    q_approval.filter.return_value = q_approval
    q_approval.all.return_value = approvals

    q_user = MagicMock()
    q_user.filter.return_value = q_user
    # _send_medium/strong 里可能多次 db.query(User) 调用，统一返回同一 submitter
    q_user.first.return_value = submitter

    def _query(model, *args, **kwargs):
        if model.__name__ == "Approval":
            return q_approval
        if model.__name__ == "User":
            return q_user
        m = MagicMock()
        return m

    db.query.side_effect = _query
    return db


def _make_scheduler():
    """每次测试用全新 scheduler，避免 _sent_reminders 跨用例污染。"""
    return ApprovalReminderScheduler()


def _patch_notification(monkeypatch, captured_reminder: dict, captured_alert: dict):
    """把 NotificationService 替换成捕获 kwargs 的 AsyncMock 实例工厂。"""
    fake_instance = MagicMock()
    fake_instance.notify_approval_reminder = AsyncMock(side_effect=lambda **kw: captured_reminder.update(kw) or True)
    fake_instance.notify_approval_timeout_alert = AsyncMock(side_effect=lambda **kw: captured_alert.update(kw) or True)
    fake_cls = MagicMock(return_value=fake_instance)
    monkeypatch.setattr("app.tasks.approval_reminder.NotificationService", fake_cls)
    return fake_cls


def _patch_adapter(monkeypatch, *, entity=None, name="单据#1", get_entity=None, raises=None):
    """替换 app.tasks.approval_reminder.get_adapter。"""
    if raises is not None:
        def _raise(bt):
            raise raises
        monkeypatch.setattr("app.tasks.approval_reminder.get_adapter", _raise)
        return

    adapter = MagicMock()
    if get_entity is not None:
        adapter.get_entity.side_effect = get_entity
    else:
        adapter.get_entity.return_value = entity
    adapter.get_name.return_value = name
    monkeypatch.setattr("app.tasks.approval_reminder.get_adapter", lambda bt: adapter)
    return adapter


# ---------- Step 1: PAYMENT 轻度提醒 ----------------------------------------


@pytest.mark.asyncio
async def test_payment_light_reminder_uses_entity_type(monkeypatch):
    """PAYMENT 审批等待 25h（>=24, <48）→ 仅轻度提醒，entity_type=PAYMENT。"""
    approval = _make_approval(
        business_type=BusinessType.PAYMENT,
        business_id=7,
        waiting_hours=25,
    )
    db = _make_db([approval], submitter=_make_user(open_id="ou_submitter", name="提交人"))

    captured_reminder: dict = {}
    captured_alert: dict = {}
    _patch_notification(monkeypatch, captured_reminder, captured_alert)
    _patch_adapter(
        monkeypatch,
        entity=MagicMock(id=7),  # 回款实体存在
        name="回款登记#7",
    )

    sched = _make_scheduler()
    sched._get_node_approvers = MagicMock(return_value=[_make_user(open_id="ou_app1", name="审批人A")])

    monkeypatch.setattr("app.tasks.approval_reminder.SessionLocal", lambda: db)
    stats = await sched.check_approval_timeout()

    # 不应被跳过：至少发了 1 条轻度提醒
    assert stats["light_reminders"] == 1
    assert captured_reminder.get("entity_type") == BusinessType.PAYMENT
    assert captured_reminder.get("entity_name") == "回款登记#7"
    assert captured_reminder.get("business_id") == 7
    assert captured_reminder.get("reminder_level") == "light"
    # 轻度提醒不触发 timeout_alert
    assert captured_alert == {}


# ---------- Step 2: INVOICE 三级提醒全部触发 -------------------------------


@pytest.mark.asyncio
async def test_invoice_strong_reminder_carries_entity_type(monkeypatch):
    """INVOICE 审批等待 73h（>=72）→ 三级提醒全部触发，实体类型透传 INVOICE。"""
    approval = _make_approval(
        business_type=BusinessType.INVOICE,
        business_id=3,
        waiting_hours=73,
    )
    submitter = _make_user(open_id="ou_submitter", name="提交人", uid=2)
    db = _make_db([approval], submitter=submitter)

    # 多级提醒会多次调用 notify_approval_reminder（light/medium/strong），
    # 用 list 收集每次 kwargs
    reminder_calls = []
    alert_calls = []
    fake_instance = MagicMock()

    async def _cap_reminder(**kw):
        reminder_calls.append(kw)
        return True

    async def _cap_alert(**kw):
        alert_calls.append(kw)
        return True

    fake_instance.notify_approval_reminder = _cap_reminder
    fake_instance.notify_approval_timeout_alert = _cap_alert
    monkeypatch.setattr(
        "app.tasks.approval_reminder.NotificationService",
        MagicMock(return_value=fake_instance),
    )
    _patch_adapter(monkeypatch, entity=MagicMock(id=3), name="发票申请#3")

    sched = _make_scheduler()
    approver = _make_user(open_id="ou_app1", name="审批人A", uid=11)
    sched._get_node_approvers = MagicMock(return_value=[approver])
    admin = _make_user(open_id="ou_admin1", name="管理员Z", uid=21)
    sched._get_team_admins = MagicMock(return_value=[admin])

    monkeypatch.setattr("app.tasks.approval_reminder.SessionLocal", lambda: db)
    stats = await sched.check_approval_timeout()

    # 三级全部触发
    assert stats["light_reminders"] == 1
    assert stats["medium_reminders"] == 1
    assert stats["strong_reminders"] == 1

    # 所有 notify_approval_reminder 调用的 entity_type 都是 INVOICE
    assert len(reminder_calls) == 3  # light + medium + strong
    levels = {c["reminder_level"] for c in reminder_calls}
    assert levels == {"light", "medium", "strong"}
    for c in reminder_calls:
        assert c["entity_type"] == BusinessType.INVOICE
        assert c["entity_name"] == "发票申请#3"
        assert c["business_id"] == 3

    # timeout_alert（提交人 + 管理员）：medium 1 + strong 2 = 3
    assert len(alert_calls) == 3
    for c in alert_calls:
        assert c["entity_type"] == BusinessType.INVOICE
        assert c["entity_name"] == "发票申请#3"
        assert c["business_id"] == 3


# ---------- Step 3: ORPHAN / 未知 business_type 跳过 -----------------------


@pytest.mark.asyncio
async def test_orphan_business_type_skips_reminder(monkeypatch):
    """business_type='ORPHAN'（未注册）→ get_adapter 抛 ValueError → 跳过，不崩也不发通知。"""
    approval = _make_approval(
        business_type="ORPHAN",
        business_id=999,
        waiting_hours=25,
    )
    db = _make_db([approval], submitter=None)

    captured_reminder: dict = {}
    captured_alert: dict = {}
    _patch_notification(monkeypatch, captured_reminder, captured_alert)
    _patch_adapter(monkeypatch, raises=ValueError("不支持的业务单据类型: ORPHAN"))

    sched = _make_scheduler()
    sched._get_node_approvers = MagicMock(return_value=[_make_user(open_id="ou", name="x")])

    monkeypatch.setattr("app.tasks.approval_reminder.SessionLocal", lambda: db)
    stats = await sched.check_approval_timeout()

    # ORPHAN 跳过，零提醒
    assert stats["light_reminders"] == 0
    assert stats["medium_reminders"] == 0
    assert stats["strong_reminders"] == 0
    assert captured_reminder == {}
    assert captured_alert == {}
    # 没崩，没有 raise（错误不进 stats["errors"]）
    assert stats["errors"] == []


# ---------- Step 4: 业务单据被删（get_entity 返 None）跳过 -----------------


@pytest.mark.asyncio
async def test_entity_deleted_skips_reminder(monkeypatch):
    """get_entity 返 None（单据被软删/跨 team）→ 跳过，不发通知，对齐原"合同不存在"语义。"""
    approval = _make_approval(
        business_type=BusinessType.PAYMENT,
        business_id=404,
        waiting_hours=25,
    )
    db = _make_db([approval], submitter=None)

    captured_reminder: dict = {}
    captured_alert: dict = {}
    _patch_notification(monkeypatch, captured_reminder, captured_alert)
    _patch_adapter(
        monkeypatch,
        entity=None,  # 单据不存在
        name="回款登记#404",
    )

    sched = _make_scheduler()
    sched._get_node_approvers = MagicMock(return_value=[_make_user(open_id="ou", name="x")])

    monkeypatch.setattr("app.tasks.approval_reminder.SessionLocal", lambda: db)
    stats = await sched.check_approval_timeout()

    assert stats["light_reminders"] == 0
    assert captured_reminder == {}
    assert captured_alert == {}
    assert stats["errors"] == []


# ---------- Step 5: CONTRACT 回归仍正常 ------------------------------------


@pytest.mark.asyncio
async def test_contract_reminder_still_works(monkeypatch):
    """CONTRACT 审批回归：泛化后仍能催办，entity_type=CONTRACT。"""
    approval = _make_approval(
        business_type=BusinessType.CONTRACT,
        business_id=100,
        waiting_hours=25,
    )
    db = _make_db([approval], submitter=_make_user(open_id="ou_sub", name="提交人"))

    captured_reminder: dict = {}
    captured_alert: dict = {}
    _patch_notification(monkeypatch, captured_reminder, captured_alert)
    _patch_adapter(monkeypatch, entity=MagicMock(id=100), name="测试合同")

    sched = _make_scheduler()
    sched._get_node_approvers = MagicMock(return_value=[_make_user(open_id="ou_app", name="审批人")])

    monkeypatch.setattr("app.tasks.approval_reminder.SessionLocal", lambda: db)
    stats = await sched.check_approval_timeout()

    assert stats["light_reminders"] == 1
    assert captured_reminder.get("entity_type") == BusinessType.CONTRACT
    assert captured_reminder.get("entity_name") == "测试合同"
    assert captured_reminder.get("business_id") == 100