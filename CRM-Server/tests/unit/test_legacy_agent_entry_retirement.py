"""Legacy Feishu input is authenticated and acknowledged without business effects."""

import asyncio
import base64
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import im_bots
from app.crud.im_bot import im_inbound_event_crud
from app.services import im_feishu


def _event(kind="text"):
    event = {
        "sender": {"sender_id": {"open_id": "ou_retired"}},
        "message": {
            "message_id": "om_retired",
            "message_type": "text",
            "chat_type": "p2p",
            "chat_id": "oc_retired",
            "content": json.dumps({"text": "确认记录客户沟通"}, ensure_ascii=False),
        },
    }
    event_type = "im.message.receive_v1"
    if kind == "group":
        event["message"]["chat_type"] = "group"
    elif kind == "post":
        event["message"]["message_type"] = "post"
    elif kind == "image":
        event["message"]["message_type"] = "image"
    elif kind.startswith("reaction"):
        event_type = f"im.message.reaction.{kind.removeprefix('reaction_')}_v1"
        event = {
            "message_id": "om_retired",
            "operator_type": "user",
            "user_id": {"open_id": "ou_retired"},
            "reaction_type": {"emoji_type": "Yes"},
        }
    return {
        "header": {
            "app_id": "cli_retired",
            "event_id": "evt_retired",
            "event_type": event_type,
            "token": "verification-token",
        },
        "event": event,
    }


def _encrypt(payload, key):
    raw = json.dumps(payload).encode()
    padding = 16 - len(raw) % 16
    iv = bytes(range(16))
    encryptor = Cipher(algorithms.AES(hashlib.sha256(key.encode()).digest()), modes.CBC(iv)).encryptor()
    encrypted = iv + encryptor.update(raw + bytes([padding]) * padding) + encryptor.finalize()
    return {"encrypt": base64.b64encode(encrypted).decode()}


@pytest.fixture
def retired_feishu(monkeypatch):
    config = SimpleNamespace(
        team_id=7, app_id="cli_retired", provider="feishu", bot_enabled=True,
        bot_verification_token="verification-token", bot_encrypt_key="encrypt-key",
    )
    monkeypatch.setattr(im_feishu.oauth_provider_config_crud, "get_by_app_id", Mock(return_value=config))
    monkeypatch.setattr(im_feishu.oauth_provider_config_crud, "get_by_verification_token", Mock(return_value=config))
    monkeypatch.setattr(im_feishu.oauth_provider_config_crud, "list_with_encrypt_key", Mock(return_value=[config]))
    boundaries = []
    for target, names in [
        (im_inbound_event_crud, ["create_received", "mark_status"]),
        (im_feishu.agent_channel_session_crud, ["get_or_create", "mark_message"]),
        (im_feishu.user_oauth_account_crud, ["get_by_open_id"]),
    ]:
        for name in names:
            boundary = Mock(side_effect=AssertionError(f"retired entry called {name}"))
            monkeypatch.setattr(target, name, boundary)
            boundaries.append(boundary)
    service = im_feishu.FeishuBotService()
    for target, names in [
        (im_feishu.im_agent_gateway, ["handle_text", "handle_reaction"]),
        (service, ["reply_text", "add_message_reaction"]),
    ]:
        for name in names:
            boundary = AsyncMock(side_effect=AssertionError(f"retired entry called {name}"))
            monkeypatch.setattr(target, name, boundary)
            boundaries.append(boundary)
    return SimpleNamespace(service=service, config=config, db=Mock(), boundaries=boundaries)


@pytest.mark.parametrize("bot_enabled", [False, True])
@pytest.mark.parametrize("encrypted", [False, True])
@pytest.mark.parametrize("kind", ["text", "group", "post", "image", "reaction_created", "reaction_deleted"])
def test_retired_business_events_have_no_side_effects(retired_feishu, bot_enabled, encrypted, kind):
    harness = retired_feishu
    harness.config.bot_enabled = bot_enabled
    payload = _event(kind)
    if encrypted:
        payload = _encrypt(payload, harness.config.bot_encrypt_key)
    for _ in range(2):  # Duplicate delivery must not create an inbound record either.
        result = asyncio.run(harness.service.handle_event(harness.db, payload, json.dumps(payload).encode()))
        assert result == {"message": "bot retired"}
    for boundary in harness.boundaries:
        boundary.assert_not_called()
    assert harness.db.mock_calls == []


@pytest.mark.parametrize("encrypted", [False, True])
@pytest.mark.parametrize("app_id", [None, "cli_retired"])
def test_url_verification_still_returns_challenge(retired_feishu, encrypted, app_id):
    harness = retired_feishu
    payload = {"type": "url_verification", "challenge": "challenge-value", "token": "verification-token"}
    if app_id:
        payload["header"] = {"app_id": app_id}
    if encrypted:
        payload = _encrypt(payload, harness.config.bot_encrypt_key)
    assert asyncio.run(harness.service.handle_event(harness.db, payload, b"")) == {"challenge": "challenge-value"}
    for boundary in harness.boundaries:
        boundary.assert_not_called()


@pytest.mark.parametrize("bot_enabled", [False, True])
@pytest.mark.parametrize("invalid", ["token", "app_id", "missing_config", "event_id", "encryption"])
def test_retirement_does_not_bypass_source_validation(retired_feishu, monkeypatch, bot_enabled, invalid):
    harness = retired_feishu
    harness.config.bot_enabled = bot_enabled
    payload = _event()
    if invalid == "token":
        payload["header"]["token"] = "invalid"
    elif invalid == "app_id":
        payload["header"]["app_id"] = "other-team-app"
    elif invalid == "missing_config":
        monkeypatch.setattr(im_feishu.oauth_provider_config_crud, "get_by_app_id", Mock(return_value=None))
    elif invalid == "event_id":
        payload["header"].pop("event_id")
        payload["event"]["message"].pop("message_id")
    else:
        payload = {"encrypt": "not-a-valid-encrypted-event"}
    with pytest.raises(im_feishu.FeishuBotEventError):
        asyncio.run(harness.service.handle_event(harness.db, payload, b""))
    for boundary in harness.boundaries:
        boundary.assert_not_called()


@pytest.mark.parametrize("invalid", [False, True])
def test_webhook_http_ack_and_validation_error(retired_feishu, monkeypatch, invalid):
    harness = retired_feishu
    app = FastAPI()
    app.include_router(im_bots.router)
    app.dependency_overrides[im_bots.get_db] = lambda: harness.db
    monkeypatch.setattr(im_bots, "feishu_bot_service", harness.service)
    payload = _event()
    if invalid:
        payload["header"]["token"] = "invalid"
    response = TestClient(app).post("/v1/im/feishu/events", json=payload)
    assert response.status_code == (400 if invalid else 200)
    if not invalid:
        assert response.json() == {"code": 0, "msg": "bot retired"}
    for boundary in harness.boundaries:
        boundary.assert_not_called()
