from __future__ import annotations

import pytest

from app.core.config import Settings
from app.services.customer_embedding_service import CustomerEmbeddingService, CustomerEmbeddingUnavailableError


class FakeSettings:
    QDRANT_VECTOR_SIZE = 1024
    CUSTOMER_EVIDENCE_EMBEDDING_MODEL = "Qwen/Qwen3-Embedding-0.6B"
    CUSTOMER_EVIDENCE_EMBEDDING_DIMENSIONS = 1024
    CUSTOMER_EVIDENCE_EMBEDDING_API_HOST = "https://api.siliconflow.cn/v1"

    def __init__(self, api_key: str = "embedding-key", api_host: str | None = None) -> None:
        self._api_key = api_key
        if api_host is not None:
            self.CUSTOMER_EVIDENCE_EMBEDDING_API_HOST = api_host

    def get_customer_evidence_embedding_api_key(self) -> str:
        return self._api_key

    def get_customer_evidence_embedding_base_url(self) -> str:
        return self.CUSTOMER_EVIDENCE_EMBEDDING_API_HOST

    def get_customer_evidence_embedding_dimensions(self) -> int:
        return self.CUSTOMER_EVIDENCE_EMBEDDING_DIMENSIONS


class FakeAIConfigCrud:
    get_config_called = False
    get_decrypted_api_key_called = False

    def get_config(self, db, team_id: int):
        self.get_config_called = True
        return type("AIConfig", (), {"api_host": "https://example.invalid/v1"})()

    def get_decrypted_api_key(self, db, team_id: int) -> str:
        self.get_decrypted_api_key_called = True
        return "test-key"


class FailingEmbeddings:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs

    def embed_query(self, text: str):
        raise RuntimeError("model not found")


class SuccessfulEmbeddings:
    calls: list[dict[str, object]] = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.calls.append(kwargs)

    def embed_query(self, text: str):
        return [0.1, 0.2, 0.3]


class MissingAIConfigCrud:
    def get_config(self, db, team_id: int):
        return None

    def get_decrypted_api_key(self, db, team_id: int) -> str:
        return ""


def test_customer_embedding_service_uses_dedicated_embedding_env_config(monkeypatch) -> None:
    SuccessfulEmbeddings.calls = []
    ai_config_crud = FakeAIConfigCrud()
    monkeypatch.setattr("app.services.customer_embedding_service.OpenAIEmbeddings", SuccessfulEmbeddings)
    monkeypatch.setattr("app.services.customer_embedding_service.get_settings", lambda: FakeSettings())
    monkeypatch.setattr("app.services.customer_embedding_service.ai_config_crud", ai_config_crud)

    vector = CustomerEmbeddingService().embed_query(object(), 2, "客户概况")

    assert vector == [0.1, 0.2, 0.3]
    assert SuccessfulEmbeddings.calls == [
        {
            "model": "Qwen/Qwen3-Embedding-0.6B",
            "api_key": "embedding-key",
            "base_url": "https://api.siliconflow.cn/v1",
            "dimensions": 1024,
        }
    ]
    assert ai_config_crud.get_config_called is False
    assert ai_config_crud.get_decrypted_api_key_called is False


def test_customer_embedding_service_falls_back_to_team_ai_config_when_embedding_key_missing(monkeypatch) -> None:
    SuccessfulEmbeddings.calls = []
    monkeypatch.setattr("app.services.customer_embedding_service.OpenAIEmbeddings", SuccessfulEmbeddings)
    monkeypatch.setattr("app.services.customer_embedding_service.get_settings", lambda: FakeSettings(api_key="", api_host=""))
    monkeypatch.setattr("app.services.customer_embedding_service.ai_config_crud", FakeAIConfigCrud())

    vector = CustomerEmbeddingService().embed_query(object(), 2, "客户概况")

    assert vector == [0.1, 0.2, 0.3]
    assert SuccessfulEmbeddings.calls[0]["api_key"] == "test-key"
    assert SuccessfulEmbeddings.calls[0]["base_url"] == "https://example.invalid/v1"


def test_customer_embedding_service_requires_embedding_key_or_team_fallback(monkeypatch) -> None:
    monkeypatch.setattr("app.services.customer_embedding_service.OpenAIEmbeddings", SuccessfulEmbeddings)
    monkeypatch.setattr("app.services.customer_embedding_service.get_settings", lambda: FakeSettings(api_key="", api_host=""))
    monkeypatch.setattr("app.services.customer_embedding_service.ai_config_crud", MissingAIConfigCrud())

    with pytest.raises(CustomerEmbeddingUnavailableError, match="API Key"):
        CustomerEmbeddingService().embed_query(object(), 2, "客户概况")


def test_customer_embedding_api_key_file_falls_back_to_env_key_when_file_missing() -> None:
    settings = Settings(
        CUSTOMER_EVIDENCE_EMBEDDING_API_KEY="env-key",
        CUSTOMER_EVIDENCE_EMBEDDING_API_KEY_FILE="/tmp/crmwolf-missing-embedding-key",
    )

    assert settings.get_customer_evidence_embedding_api_key() == "env-key"


def test_customer_embedding_service_converts_provider_failure_to_unavailable(monkeypatch) -> None:
    monkeypatch.setattr("app.services.customer_embedding_service.OpenAIEmbeddings", FailingEmbeddings)
    monkeypatch.setattr("app.services.customer_embedding_service.get_settings", lambda: FakeSettings())
    monkeypatch.setattr("app.services.customer_embedding_service.ai_config_crud", FakeAIConfigCrud())

    with pytest.raises(CustomerEmbeddingUnavailableError):
        CustomerEmbeddingService().embed_query(object(), 2, "客户概况")
