import redis
from redis import asyncio as aioredis
from typing import Optional
from app.core.config import get_settings

settings = get_settings()

redis_client: Optional[redis.Redis] = None
async_redis_client: Optional[aioredis.Redis] = None


def get_redis_client() -> redis.Redis:
    global redis_client
    if redis_client is None:
        redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
            db=settings.REDIS_DB,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True
        )
    return redis_client


async def get_async_redis_client() -> aioredis.Redis:
    global async_redis_client
    if async_redis_client is None:
        async_redis_client = await aioredis.from_url(
            f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}",
            password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5
        )
    return async_redis_client


async def get_redis() -> aioredis.Redis:
    """FastAPI 依赖：获取 Redis client"""
    return await get_async_redis_client()


async def close_redis_connections():
    global redis_client, async_redis_client
    if redis_client:
        redis_client.close()
        redis_client = None
    if async_redis_client:
        await async_redis_client.close()
        async_redis_client = None
