# ruff: noqa: RUF001
"""HTTP contract for assistant image attachments: upload, GET ownership, vision extraction, and fail-closed reuse."""

import base64
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import BigInteger

from app.api import assistant as api
from app.core import deps
from app.core.database import Base, get_db
from app.main import app
from app.models.assistant import AssistantAction, AssistantTask
from app.models.assistant_conversation import AssistantConversation, AssistantConversationEntry
from app.models.assistant_turn import AssistantRequest, AssistantTurn, AssistantTurnEvent
from app.schemas.assistant_conversation import ConversationAttachmentRef, ConversationDecision
from app.services.assistant import conversation as conversation_module
from app.services.assistant import turns
from app.services.assistant import vision as vision_module
from app.services.assistant.conversation import ConversationService
from app.services.assistant.failure_contract import AssistantFailureCode
from app.services.assistant.vision import (
    VISION_UNSUPPORTED_MESSAGE,
    OpenAIAttachmentVisionExtractor,
    VisionUnsupportedError,
)
from app.services.file_storage import FileStorageService

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
UPLOAD_URL = "/api/v1/assistant/attachments"
MESSAGES_URL = "/api/v1/assistant/conversation/messages"


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


class _Root:
    def __init__(self) -> None:
        self.seen_texts: list[str] = []

    async def classify(self, db, **kwargs):
        self.seen_texts.append(kwargs["text"])
        return ConversationDecision(
            semantic_plan={
                "speech_act": "ASSERT_EVENT",
                "business_object": "CUSTOMER_ACTIVITY",
                "operation": "CREATE",
                "confidence": 0.95,
            },
            task_relation="NEW_TASK",
            route="WORKFLOW",
            boundary="NEW",
            confidence=0.95,
        )


class _FakeVision:
    def __init__(self, result: str = "图1：张总（睿狐科技）微信确认周五上午10点演示二期方案。") -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []
        self.error: Exception | None = None

    async def extract(self, db, *, team_id: int, user_id: int, attachments, user_text: str) -> str:
        self.calls.append({"team_id": team_id, "user_id": user_id, "attachments": attachments, "user_text": user_text})
        if self.error is not None:
            raise self.error
        return self.result

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(
        engine,
        tables=[
            AssistantTask.__table__,
            AssistantAction.__table__,
            AssistantRequest.__table__,
            AssistantTurn.__table__,
            AssistantTurnEvent.__table__,
            AssistantConversation.__table__,
            AssistantConversationEntry.__table__,
        ],
    )
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def upload_dir(tmp_path, monkeypatch) -> Path:
    monkeypatch.setattr(api, "file_storage_service", FileStorageService(base_dir=str(tmp_path)))
    return tmp_path


@pytest.fixture
def root_classifier() -> _Root:
    return _Root()


@pytest.fixture
def fake_vision() -> _FakeVision:
    return _FakeVision()


@pytest.fixture
def client(db_session, upload_dir, root_classifier, fake_vision, monkeypatch):
    def _get_db_override():
        yield db_session

    monkeypatch.setattr(turns, "SessionLocal", sessionmaker(bind=db_session.get_bind(), autoflush=False))
    monkeypatch.setattr(
        api,
        "_conversation_service",
        ConversationService(classifier=root_classifier, vision_extractor=fake_vision),
    )
    monkeypatch.setattr(conversation_module, "schedule_turn", lambda turn_id: None)
    app.dependency_overrides[deps.get_current_active_user] = lambda: SimpleNamespace(id=2, team_id=1)
    app.dependency_overrides[deps.get_current_user_team] = lambda: 1
    app.dependency_overrides[get_db] = _get_db_override
    # Conversation routes forward the session bearer to CRM reads, as the browser always sends it.
    yield TestClient(app, headers={"Authorization": "Bearer test-token"})
    for dependency in (deps.get_current_active_user, deps.get_current_user_team, get_db):
        app.dependency_overrides.pop(dependency, None)

def _stored_files(root: Path) -> list[Path]:
    return [path for path in root.rglob("*") if path.is_file()]


def _send_text(client: TestClient, attachment: dict[str, object], request_id: str, text: str = "看下这张微信截图"):
    version = client.post("/api/v1/assistant/conversation/open").json()["version"]
    return client.post(
        MESSAGES_URL,
        json={
            "text": text,
            "client_request_id": request_id,
            "expected_version": version,
            "attachments": [attachment],
        },
    )


def test_upload_stores_png_under_team_and_user(client, upload_dir):
    response = client.post(UPLOAD_URL, files={"file": ("wechat.png", PNG_BYTES, "image/png")})

    assert response.status_code == 200
    body = response.json()
    assert body["file_url"].startswith("assistant_attachments/1/2/")
    assert body["file_url"].endswith(".png")
    assert body | {"file_url": None} == {
        "file_url": None,
        "file_name": "wechat.png",
        "mime_type": "image/png",
        "size_bytes": len(PNG_BYTES),
    }
    assert (upload_dir / body["file_url"]).read_bytes() == PNG_BYTES


def test_upload_rejects_non_image_declared_as_png(client, upload_dir):
    response = client.post(UPLOAD_URL, files={"file": ("fake.png", b"<html>not an image</html>", "image/png")})

    assert response.status_code == 422
    assert _stored_files(upload_dir) == []


def test_upload_rejects_image_over_10mb(client, upload_dir):
    oversized = PNG_BYTES + b"\x00" * (10_485_760 + 1 - len(PNG_BYTES))

    response = client.post(UPLOAD_URL, files={"file": ("big.png", oversized, "image/png")})

    assert response.status_code == 422
    assert _stored_files(upload_dir) == []


def test_text_accepts_own_uploaded_attachment(client, db_session):
    uploaded = client.post(UPLOAD_URL, files={"file": ("wechat.png", PNG_BYTES, "image/png")}).json()

    response = _send_text(client, uploaded, "attachment-own-0001")

    assert response.status_code == 200
    assert db_session.query(AssistantTurn).count() == 1


@pytest.mark.parametrize(
    "file_url",
    [
        "assistant_attachments/1/3/other-user.png",
        "assistant_attachments/9/2/other-team.png",
        "assistant_attachments/1/2/../3/other-user.png",
        "assistant_attachments/1/2/missing.png",
    ],
    ids=["other-user", "other-team", "path-traversal", "nonexistent"],
)
def test_text_rejects_attachment_not_owned_or_missing(client, db_session, upload_dir, file_url):
    for foreign in ("assistant_attachments/1/3/other-user.png", "assistant_attachments/9/2/other-team.png"):
        (upload_dir / foreign).parent.mkdir(parents=True, exist_ok=True)
        (upload_dir / foreign).write_bytes(PNG_BYTES)
    attachment = {"file_url": file_url, "file_name": "x.png", "mime_type": "image/png", "size_bytes": len(PNG_BYTES)}

    response = _send_text(client, attachment, "attachment-deny-0001")

    assert response.status_code == 422
    assert response.json()["detail"] == "附件不存在或无权使用"
    assert db_session.query(AssistantTurn).count() == 0


def test_get_attachment_serves_own_image_and_denies_other_owners(client, upload_dir):
    uploaded = client.post(UPLOAD_URL, files={"file": ("wechat.png", PNG_BYTES, "image/png")}).json()
    stored_name = uploaded["file_url"].split("/")[-1]

    ok = client.get(f"{UPLOAD_URL}/{stored_name}")
    assert ok.status_code == 200
    assert ok.headers["content-type"] == "image/png"
    assert ok.content == PNG_BYTES

    # Another user in the same team cannot read user 2's file.
    app.dependency_overrides[deps.get_current_active_user] = lambda: SimpleNamespace(id=3, team_id=1)
    assert client.get(f"{UPLOAD_URL}/{stored_name}").status_code == 404

    # Another team cannot read team 1's file.
    app.dependency_overrides[deps.get_current_active_user] = lambda: SimpleNamespace(id=2, team_id=9)
    app.dependency_overrides[deps.get_current_user_team] = lambda: 9
    assert client.get(f"{UPLOAD_URL}/{stored_name}").status_code == 404

    # Restore owner and reject traversal / missing.
    app.dependency_overrides[deps.get_current_active_user] = lambda: SimpleNamespace(id=2, team_id=1)
    app.dependency_overrides[deps.get_current_user_team] = lambda: 1
    assert client.get(f"{UPLOAD_URL}/..%2F3%2Fother.png").status_code == 404
    assert client.get(f"{UPLOAD_URL}/missing.png").status_code == 404


def test_image_only_message_runs_vision_and_exposes_user_attachments(client, db_session, root_classifier, fake_vision):
    uploaded = client.post(UPLOAD_URL, files={"file": ("card.png", PNG_BYTES, "image/png")}).json()

    response = _send_text(client, uploaded, "attachment-only-0001", text="")

    assert response.status_code == 200
    assert len(fake_vision.calls) == 1
    assert "张总（睿狐科技）" in root_classifier.seen_texts[0]
    messages = response.json()["conversation"]["messages"]
    user_messages = [msg for msg in messages if msg["role"] == "user"]
    assert len(user_messages) == 1
    assert user_messages[0]["text"] == ""
    assert user_messages[0]["attachments"] == [uploaded]
    assert db_session.query(AssistantTurn).count() == 1


def test_vision_unsupported_error_surfaces_actionable_copy(client, db_session, fake_vision):
    fake_vision.error = VisionUnsupportedError(
        VISION_UNSUPPORTED_MESSAGE, code=AssistantFailureCode.REQUEST_PROTOCOL_ERROR
    )
    uploaded = client.post(UPLOAD_URL, files={"file": ("wechat.png", PNG_BYTES, "image/png")}).json()

    response = _send_text(client, uploaded, "attachment-vision-err-0001")

    assert response.status_code == 200
    assistant_messages = [msg for msg in response.json()["conversation"]["messages"] if msg["role"] == "assistant"]
    assert assistant_messages[-1]["outcome"] == "failure"
    assert assistant_messages[-1]["text"] == VISION_UNSUPPORTED_MESSAGE
    error_block = assistant_messages[-1]["ui"]["blocks"][0]
    assert error_block["type"] == "error"
    assert error_block["code"] == "REQUEST_PROTOCOL_ERROR"
    assert error_block["retryable"] is False
    assert error_block["message"] == VISION_UNSUPPORTED_MESSAGE


@pytest.mark.asyncio
async def test_openai_vision_extractor_sends_base64_data_uri_and_maps_protocol_error(tmp_path, monkeypatch):
    storage = FileStorageService(base_dir=str(tmp_path))
    stored_url = storage.save_assistant_attachment(team_id=1, user_id=2, filename="card.png", content=PNG_BYTES)
    ref = ConversationAttachmentRef(
        file_url=stored_url, file_name="card.png", mime_type="image/png", size_bytes=len(PNG_BYTES)
    )
    captured: dict[str, object] = {}

    class _MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url: str, *, headers=None, json=None):
            captured["url"] = url
            captured["json"] = json
            status_code = int(captured.get("status_code", 200))
            if status_code != 200:
                return httpx.Response(status_code, json={"error": {"message": "image_url not supported"}})
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "图1：王经理，电话13800138000"}}]},
            )

    monkeypatch.setattr(
        vision_module, "team_model_credentials", lambda db, team_id: ("https://ai.test/v1", "sk-test", "gpt-4o")
    )
    monkeypatch.setattr(vision_module.httpx, "AsyncClient", _MockAsyncClient)

    extractor = OpenAIAttachmentVisionExtractor(storage=storage)
    text = await extractor.extract(None, team_id=1, user_id=2, attachments=[ref], user_text="帮我记一下名片")
    assert text == "图1：王经理，电话13800138000"
    expected_uri = f"data:image/png;base64,{base64.b64encode(PNG_BYTES).decode('ascii')}"
    user_content = captured["json"]["messages"][1]["content"]
    assert user_content[1] == {"type": "image_url", "image_url": {"url": expected_uri}}

    captured["status_code"] = 400
    with pytest.raises(VisionUnsupportedError, match="暂不支持图片识别"):
        await extractor.extract(None, team_id=1, user_id=2, attachments=[ref], user_text="")
