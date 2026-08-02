from __future__ import annotations

import pytest

from app.services.customer_embedding_service import CustomerEmbeddingService, CustomerEmbeddingUnavailableError


class FakeAIConfigCrud:
    def get_config(self, db, team_id: int):
        return type("AIConfig", (), {"api_host": "https://example.invalid/v1"})()

    def get_decrypted_api_key(self, db, team_id: int) -> str:
        return "test-key"


class FailingEmbeddings:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs

    def embed_query(self, text: str):
        raise RuntimeError("model not found")


def test_customer_embedding_service_converts_provider_failure_to_unavailable(monkeypatch) -> None:
    monkeypatch.setattr("app.services.customer_embedding_service.OpenAIEmbeddings", FailingEmbeddings)
    monkeypatch.setattr("app.services.customer_embedding_service.ai_config_crud", FakeAIConfigCrud())

    with pytest.raises(CustomerEmbeddingUnavailableError):
        CustomerEmbeddingService().embed_query(object(), 2, "客户概况")
