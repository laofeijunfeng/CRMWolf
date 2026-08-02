"""Embedding provider for customer intelligence evidence."""

from collections.abc import Sequence
import logging

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.crud.ai_config import ai_config_crud

try:
    from langchain_openai import OpenAIEmbeddings
except Exception:  # pragma: no cover - optional production dependency
    OpenAIEmbeddings = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class CustomerEmbeddingUnavailableError(Exception):
    """Raised when customer evidence embedding cannot be produced."""


class CustomerEmbeddingService:
    def embed_query(self, db: Session, team_id: int, text: str) -> Sequence[float]:
        if OpenAIEmbeddings is None:
            raise CustomerEmbeddingUnavailableError("langchain_openai OpenAIEmbeddings 不可用")

        settings = get_settings()
        api_key = settings.get_customer_evidence_embedding_api_key()
        base_url = settings.get_customer_evidence_embedding_base_url()

        if not api_key:
            ai_config = ai_config_crud.get_config(db, team_id)
            api_key = ai_config_crud.get_decrypted_api_key(db, team_id)
            base_url = base_url or (ai_config.api_host if ai_config is not None else "")

        if not api_key:
            raise CustomerEmbeddingUnavailableError("客户证据向量模型未配置 API Key")
        if not base_url:
            raise CustomerEmbeddingUnavailableError("客户证据向量模型未配置 API Host")

        embeddings = OpenAIEmbeddings(
            model=settings.CUSTOMER_EVIDENCE_EMBEDDING_MODEL,
            api_key=api_key,
            base_url=base_url,
            dimensions=settings.get_customer_evidence_embedding_dimensions(),
        )
        try:
            return embeddings.embed_query(text)
        except Exception as exc:
            logger.info(
                "客户证据向量生成不可用: team_id=%s, model=%s, reason=%s",
                team_id,
                settings.CUSTOMER_EVIDENCE_EMBEDDING_MODEL,
                exc.__class__.__name__,
            )
            raise CustomerEmbeddingUnavailableError(str(exc)) from exc


customer_embedding_service = CustomerEmbeddingService()
