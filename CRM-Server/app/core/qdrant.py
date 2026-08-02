from functools import lru_cache

from qdrant_client import QdrantClient

from app.core.config import get_settings


@lru_cache(maxsize=1)
def get_qdrant_client() -> QdrantClient:
    settings = get_settings()
    return QdrantClient(
        host=settings.QDRANT_HOST,
        port=settings.QDRANT_PORT,
        api_key=settings.QDRANT_API_KEY or None,
        timeout=settings.QDRANT_TIMEOUT_SECONDS,
    )


def reset_qdrant_client() -> None:
    get_qdrant_client.cache_clear()
