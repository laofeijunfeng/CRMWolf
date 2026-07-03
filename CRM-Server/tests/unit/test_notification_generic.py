"""Task A8：通知模板泛化单元测试。

覆盖：
- notify_approval_pending 接受 entity_type/entity_name/business_id 泛化参数，
  透传给 feishu_service.notify_approval_pending（API 分支）
- 旧合同别名 contract_name/contract_id 仍可用（向后兼容）
- notify_approval_approved / notify_approval_rejected 同模式
- Webhook 分支：notify_approval_pending 调 feishu_service.notify_approval_webhook，
  payload 含 entity_type / business_id
"""
import pytest

from unittest.mock import AsyncMock, MagicMock

from app.services.notification import NotificationService


# ---------- helpers --------------------------------------------------------


def _service_with_api(monkeypatch, captured: dict) -> NotificationService:
    """构造 NotificationService，config 走 API 分支，feishu_service.notify_approval_*
    被 monkeypatch 成捕获 kwargs 的协程。"""
    svc = NotificationService.__new__(NotificationService)
    svc.db = MagicMock()
    svc.team_id = 1

    cfg = MagicMock()
    cfg.notification_method = "api"
    svc._config = cfg

    async def _capture_pending(**kw):
        captured.update(kw)
        return True

    async def _capture_approved(**kw):
        captured.update(kw)
        return True

    async def _capture_rejected(**kw):
        captured.update(kw)
        return True

    monkeypatch.setattr(
        "app.services.notification.feishu_service.notify_approval_pending",
        _capture_pending,
    )
    monkeypatch.setattr(
        "app.services.notification.feishu_service.notify_approval_approved",
        _capture_approved,
    )
    monkeypatch.setattr(
        "app.services.notification.feishu_service.notify_approval_rejected",
        _capture_rejected,
    )
    return svc


def _service_with_webhook(monkeypatch, captured: dict) -> NotificationService:
    """构造走 webhook 分支的 service，捕获 notify_approval_webhook 的 kwargs。"""
    svc = NotificationService.__new__(NotificationService)
    svc.db = MagicMock()
    svc.team_id = 1

    cfg = MagicMock()
    cfg.notification_method = "webhook"
    cfg.feishu_webhook_url = "https://example.com/hook"
    cfg.feishu_webhook_enabled = True
    svc._config = cfg

    async def _capture_webhook(**kw):
        captured.update(kw)
        return True

    monkeypatch.setattr(
        "app.services.notification.feishu_service.notify_approval_webhook",
        _capture_webhook,
    )
    return svc


# ---------- Step 1: pending uses entity_name / business_id (API) -----------

@pytest.mark.asyncio
async def test_notify_pending_uses_entity_name(monkeypatch):
    captured: dict = {}
    svc = _service_with_api(monkeypatch, captured)

    await svc.notify_approval_pending(
        entity_type="INVOICE",
        entity_name="发票申请#1",
        flow_name="F",
        node_name="N",
        approver_open_id="o",
        approver_name="x",
        business_id=1,
    )
    assert captured.get("entity_name") == "发票申请#1"
    assert captured.get("business_id") == 1
    assert captured.get("entity_type") == "INVOICE"


@pytest.mark.asyncio
async def test_notify_pending_legacy_alias_compat(monkeypatch):
    """旧调用方传 contract_name / contract_id 仍可工作，内部映射到 entity_name / business_id。"""
    captured: dict = {}
    svc = _service_with_api(monkeypatch, captured)

    await svc.notify_approval_pending(
        contract_name="合同A",
        flow_name="F",
        node_name="N",
        approver_open_id="o",
        approver_name="x",
        contract_id=42,
    )
    # 透传到 feishu_service 的是新签名
    assert captured.get("entity_name") == "合同A"
    assert captured.get("business_id") == 42


# ---------- approved / rejected 同模式 ------------------------------------

@pytest.mark.asyncio
async def test_notify_approved_uses_entity_name(monkeypatch):
    captured: dict = {}
    svc = _service_with_api(monkeypatch, captured)

    await svc.notify_approval_approved(
        submitter_open_id="o",
        entity_type="PAYMENT",
        entity_name="回款登记#9",
        business_id=9,
    )
    assert captured.get("entity_name") == "回款登记#9"
    assert captured.get("business_id") == 9


@pytest.mark.asyncio
async def test_notify_approved_legacy_alias_compat(monkeypatch):
    captured: dict = {}
    svc = _service_with_api(monkeypatch, captured)

    await svc.notify_approval_approved(
        submitter_open_id="o",
        contract_name="合同A",
        contract_id=42,
    )
    assert captured.get("entity_name") == "合同A"
    assert captured.get("business_id") == 42


@pytest.mark.asyncio
async def test_notify_rejected_uses_entity_name(monkeypatch):
    captured: dict = {}
    svc = _service_with_api(monkeypatch, captured)

    await svc.notify_approval_rejected(
        submitter_open_id="o",
        entity_type="INVOICE",
        entity_name="发票申请#1",
        reject_reason="金额错误",
        business_id=1,
    )
    assert captured.get("entity_name") == "发票申请#1"
    assert captured.get("business_id") == 1
    assert captured.get("reject_reason") == "金额错误"


@pytest.mark.asyncio
async def test_notify_rejected_legacy_alias_compat(monkeypatch):
    captured: dict = {}
    svc = _service_with_api(monkeypatch, captured)

    await svc.notify_approval_rejected(
        submitter_open_id="o",
        contract_name="合同A",
        reject_reason="无",
        contract_id=42,
    )
    assert captured.get("entity_name") == "合同A"
    assert captured.get("business_id") == 42


# ---------- Webhook 分支 payload 含 entity_type / business_id ---------------

@pytest.mark.asyncio
async def test_notify_pending_webhook_carries_entity_fields(monkeypatch):
    captured: dict = {}
    svc = _service_with_webhook(monkeypatch, captured)

    await svc.notify_approval_pending(
        entity_type="INVOICE",
        entity_name="发票申请#1",
        flow_name="F",
        node_name="N",
        approver_open_id="o",
        approver_name="x",
        business_id=1,
    )
    assert captured.get("entity_type") == "INVOICE"
    assert captured.get("entity_name") == "发票申请#1"
    assert captured.get("business_id") == 1


# ---------- feishu_service 旧合同位置参数兼容（crud/contract.py:71 路径） ----

@pytest.mark.asyncio
async def test_feishu_pending_legacy_positional_compat(monkeypatch):
    """crud/contract.py:71 用位置参数 (user_id, contract_name, flow_name,
    node_name) 调 feishu_service.notify_approval_pending —— 仍需正确解析为
    CONTRACT 类型 + entity_name=contract_name，不能错位到 entity_type。"""
    from app.services.feishu import feishu_service

    captured: dict = {}

    async def _fake_send_message_card(user_id, title, content, tenant_access_token=None):
        captured["user_id"] = user_id
        captured["title"] = title
        captured["content"] = content
        return True

    monkeypatch.setattr(
        feishu_service, "send_message_card", _fake_send_message_card
    )

    # 模拟 crud/contract.py 的位置参数调用
    await feishu_service.notify_approval_pending(
        "ou_test", "合同A", "合同审批流程", "财务审批"
    )
    # 标题里不能出现"单据"（说明 entity_type 未被错位为合同名）
    assert "合同" in captured["title"]
    assert "单据" not in captured["title"]
    # 内容含原合同名
    assert "合同A" in captured["content"]
    # 内容含流程名 / 节点名 —— 验证未错位
    assert "合同审批流程" in captured["content"]
    assert "财务审批" in captured["content"]
