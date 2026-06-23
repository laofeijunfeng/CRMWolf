"""
Redis Checkpointer for LangGraph AI Assistant

This module provides a Redis-based checkpointer with TTL support,
replacing the legacy session_store.py for LangGraph state persistence.

Key features:
- TTL-based expiration (30 minutes default)
- Automatic session cleanup
- JSON serialization for state storage
- Compatible with LangGraph's checkpointer interface

Usage:
    checkpointer = RedisCheckpointer(
        redis_url="redis://localhost:6379",
        ttl=1800  # 30 minutes
    )

    graph = StateGraph(AgentState)
    app = graph.compile(checkpointer=checkpointer)
"""

import json
import time
from typing import Any, Dict, Optional, Tuple

from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from redis import asyncio as aioredis

from app.core.config import get_settings

# Create serde instance for handling LangChain message objects
serde = JsonPlusSerializer()


class RedisCheckpointer(BaseCheckpointSaver):
    """
    Redis-based checkpointer with TTL support for LangGraph.

    Stores checkpoints in Redis with automatic expiration.
    Thread-safe for concurrent access.

    Key format: langgraph:checkpoint:{thread_id}
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        ttl: int = 1800,  # 30 minutes default
    ) -> None:
        """
        Initialize Redis checkpointer.

        Args:
            redis_url: Redis connection URL (defaults to settings.REDIS_HOST)
            ttl: Time-to-live in seconds for checkpoint expiration
        """
        settings = get_settings()
        self.redis_url = redis_url or f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}"
        self.ttl = ttl
        self._redis: Optional[aioredis.Redis] = None

    async def _get_redis(self) -> aioredis.Redis:
        """Get or create Redis connection."""
        if self._redis is None:
            self._redis = aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._redis

    def _key(self, thread_id: str) -> str:
        """Generate Redis key for a thread."""
        return f"langgraph:checkpoint:{thread_id}"

    def _metadata_key(self, thread_id: str) -> str:
        """Generate Redis key for checkpoint metadata."""
        return f"langgraph:metadata:{thread_id}"

    async def get_tuple(self, config: Dict[str, Any]) -> Optional[CheckpointTuple]:
        """
        Get the latest checkpoint tuple for a thread.

        Args:
            config: Configuration dict with thread_id in configurable

        Returns:
            CheckpointTuple if found, None otherwise
        """
        thread_id = config.get("configurable", {}).get("thread_id")
        if not thread_id:
            return None

        redis = await self._get_redis()
        key = self._key(thread_id)

        # Get checkpoint data
        data = await redis.get(key)
        if not data:
            return None

        # Parse checkpoint using LangGraph's serde (handles HumanMessage, etc.)
        checkpoint_dict = serde.loads(data)
        checkpoint = Checkpoint(
            id=checkpoint_dict["id"],
            ts=checkpoint_dict["ts"],
            channel_values=checkpoint_dict["channel_values"],
            channel_versions=checkpoint_dict["channel_versions"],
            versions_seen=checkpoint_dict["versions_seen"],
        )

        # Get metadata (optional)
        metadata_data = await redis.get(self._metadata_key(thread_id))
        metadata = None
        if metadata_data:
            metadata_dict = json.loads(metadata_data)
            metadata = CheckpointMetadata(
                source=metadata_dict.get("source"),
                step=metadata_dict.get("step"),
                writes=metadata_dict.get("writes"),
                parents=metadata_dict.get("parents"),
            )

        return CheckpointTuple(
            config=config,
            checkpoint=checkpoint,
            metadata=metadata,
            parent_config=config,  # For simplicity, same config
        )

    async def put(
        self,
        config: Dict[str, Any],
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: Dict[str, str],
    ) -> Dict[str, Any]:
        """
        Store a checkpoint for a thread.

        Args:
            config: Configuration dict with thread_id
            checkpoint: Checkpoint data to store
            metadata: Metadata to store
            new_versions: New channel versions

        Returns:
            Updated config
        """
        thread_id = config.get("configurable", {}).get("thread_id")
        if not thread_id:
            raise ValueError("thread_id required in config")

        redis = await self._get_redis()
        key = self._key(thread_id)

        # Serialize checkpoint using LangGraph's serde (handles HumanMessage, etc.)
        checkpoint_dict = {
            "id": checkpoint.id,
            "ts": checkpoint.ts,
            "channel_values": checkpoint.channel_values,
            "channel_versions": checkpoint.channel_versions,
            "versions_seen": checkpoint.versions_seen,
        }

        # Store checkpoint with TTL (use serde for LangChain objects)
        serialized = serde.dumps(checkpoint_dict)
        await redis.setex(key, self.ttl, serialized)

        # Store metadata separately
        metadata_dict = {
            "source": metadata.source,
            "step": metadata.step,
            "writes": metadata.writes,
            "parents": metadata.parents,
            "timestamp": time.time(),
        }
        await redis.setex(self._metadata_key(thread_id), self.ttl, json.dumps(metadata_dict))

        return config

    async def put_writes(
        self,
        config: Dict[str, Any],
        writes: Dict[str, Any],
        task_id: str,
        task_path: str = "",
    ) -> None:
        """
        Store writes for a pending task.

        Args:
            config: Configuration dict
            writes: Write operations to store
            task_id: Task identifier
            task_path: Task path
        """
        thread_id = config.get("configurable", {}).get("thread_id")
        if not thread_id:
            return

        redis = await self._get_redis()

        # Store writes in a list
        writes_key = f"langgraph:writes:{thread_id}:{task_id}"
        writes_dict = {
            "writes": writes,
            "task_id": task_id,
            "task_path": task_path,
            "timestamp": time.time(),
        }
        await redis.setex(writes_key, self.ttl, json.dumps(writes_dict))

    async def list(self, config: Dict[str, Any]) -> list[CheckpointTuple]:
        """
        List all checkpoints for a thread.

        For this implementation, returns only the latest checkpoint.

        Args:
            config: Configuration dict

        Returns:
            List of checkpoint tuples
        """
        result = await self.get_tuple(config)
        return [result] if result else []

    async def delete(self, config: Dict[str, Any]) -> None:
        """
        Delete checkpoint for a thread.

        Args:
            config: Configuration dict with thread_id
        """
        thread_id = config.get("configurable", {}).get("thread_id")
        if not thread_id:
            return

        redis = await self._get_redis()
        await redis.delete(self._key(thread_id))
        await redis.delete(self._metadata_key(thread_id))

    async def clear_expired(self) -> int:
        """
        Clear all expired checkpoints (maintenance operation).

        Redis TTL handles this automatically, but this method
        can be called for manual cleanup.

        Returns:
            Number of keys deleted
        """
        redis = await self._get_redis()
        pattern = "langgraph:checkpoint:*"

        # Scan for keys (non-blocking)
        keys = []
        cursor = 0
        while True:
            cursor, batch = await redis.scan(cursor, match=pattern, count=100)
            keys.extend(batch)
            if cursor == 0:
                break

        # TTL is handled by Redis, so we don't need manual deletion
        return len(keys)

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None


# ==================== Factory Function ====================


async def get_checkpointer() -> RedisCheckpointer:
    """
    Get a Redis checkpointer instance.

    Uses settings for Redis connection and TTL.

    Returns:
        RedisCheckpointer instance
    """
    settings = get_settings()
    return RedisCheckpointer(
        ttl=settings.AGENT_SESSION_TIMEOUT,  # Use same TTL as legacy session
    )