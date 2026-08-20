"""SQLAlchemy-backed LangGraph checkpointer for CRMWolf workflows."""
from __future__ import annotations

from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    get_checkpoint_id,
    get_checkpoint_metadata,
)
from sqlalchemy import Engine, text

from app.core.database import engine

WRITES_IDX_MAP = {"__error__": -1, "__scheduled__": -2, "__interrupt__": -3, "__resume__": -4}

PENDING_TASK_RUNTIME = "crm_agent_pending_task"
PENDING_TASK_NAMESPACE_PREFIX = "pending_task_subgraph:"
AGENT_ROOT_THREAD_PREFIX = "crm_agent:"


def _validate_checkpoint_persistence_contract(
    *,
    thread_id: str,
    checkpoint_ns: str,
    metadata: CheckpointMetadata,
) -> None:
    """Reject pending-task checkpoints whose physical locator is not V2-compatible."""

    runtime = metadata.get("runtime")
    runtime_namespace = metadata.get("runtime_namespace")
    if runtime != PENDING_TASK_RUNTIME and runtime_namespace != PENDING_TASK_RUNTIME:
        return

    continuation_id = metadata.get("continuation_id")
    continuation_thread_id = metadata.get("continuation_thread_id")
    continuation_checkpoint_ns = metadata.get("continuation_checkpoint_ns")
    if runtime != PENDING_TASK_RUNTIME or runtime_namespace != PENDING_TASK_RUNTIME:
        raise ValueError(
            "pending-task checkpoint metadata is inconsistent: "
            f"runtime={runtime!r}, runtime_namespace={runtime_namespace!r}"
        )
    if not thread_id.startswith(AGENT_ROOT_THREAD_PREFIX):
        raise ValueError(
            "pending-task checkpoint thread must be owned by Agent Root: "
            f"thread_id={thread_id!r}, continuation_id={continuation_id!r}"
        )
    if not checkpoint_ns.startswith(PENDING_TASK_NAMESPACE_PREFIX):
        raise ValueError(
            "pending-task checkpoint namespace must use the child namespace: "
            f"checkpoint_ns={checkpoint_ns!r}, continuation_id={continuation_id!r}"
        )
    if not isinstance(continuation_id, str) or not continuation_id:
        raise ValueError(
            "pending-task checkpoint requires a continuation identity: "
            f"thread_id={thread_id!r}, checkpoint_ns={checkpoint_ns!r}"
        )
    if continuation_thread_id != thread_id or continuation_checkpoint_ns != checkpoint_ns:
        raise ValueError(
            "pending-task continuation locator does not match its physical checkpoint: "
            f"continuation_thread_id={continuation_thread_id!r}, thread_id={thread_id!r}, "
            f"continuation_checkpoint_ns={continuation_checkpoint_ns!r}, "
            f"checkpoint_ns={checkpoint_ns!r}, continuation_id={continuation_id!r}"
        )


def _config(thread_id: str, checkpoint_ns: str, checkpoint_id: str | None = None) -> RunnableConfig:
    configurable: dict[str, Any] = {"thread_id": thread_id, "checkpoint_ns": checkpoint_ns}
    if checkpoint_id:
        configurable["checkpoint_id"] = checkpoint_id
    return {"configurable": configurable}


def _version_key(version: object) -> str:
    return str(version)


class SQLAlchemyCheckpointSaver(BaseCheckpointSaver[str]):
    """Persist LangGraph checkpoints in the existing application database."""

    def __init__(self, db_engine: Engine | None = None) -> None:
        super().__init__()
        self.engine = db_engine or engine

    def _dump(self, value: Any) -> tuple[str, bytes]:
        return self.serde.dumps_typed(value)

    def _load(self, serde_type: str, blob: bytes) -> Any:
        return self.serde.loads_typed((serde_type, blob))

    def _load_blobs(self, thread_id: str, checkpoint_ns: str, versions: ChannelVersions) -> dict[str, Any]:
        if not versions:
            return {}
        rows = []
        with self.engine.begin() as conn:
            for channel, version in versions.items():
                row = conn.execute(text("""
                    SELECT serde_type, `blob`
                    FROM crm_langgraph_checkpoint_blobs
                    WHERE thread_id = :thread_id
                      AND checkpoint_ns = :checkpoint_ns
                      AND channel = :channel
                      AND version = :version
                """), {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "channel": channel,
                    "version": _version_key(version),
                }).first()
                if row and row[0] != "empty":
                    rows.append((channel, row[0], row[1]))
        return {channel: self._load(serde_type, blob) for channel, serde_type, blob in rows}

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = get_checkpoint_id(config)
        with self.engine.begin() as conn:
            if checkpoint_id:
                row = conn.execute(text("""
                    SELECT checkpoint_id, parent_checkpoint_id, checkpoint_type, checkpoint_blob,
                           metadata_type, metadata_blob
                    FROM crm_langgraph_checkpoints
                    WHERE thread_id = :thread_id
                      AND checkpoint_ns = :checkpoint_ns
                      AND checkpoint_id = :checkpoint_id
                """), {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": checkpoint_id,
                }).first()
            else:
                row = conn.execute(text("""
                    SELECT checkpoint_id, parent_checkpoint_id, checkpoint_type, checkpoint_blob,
                           metadata_type, metadata_blob
                    FROM crm_langgraph_checkpoints
                    WHERE thread_id = :thread_id
                      AND checkpoint_ns = :checkpoint_ns
                    ORDER BY checkpoint_id DESC
                    LIMIT 1
                """), {"thread_id": thread_id, "checkpoint_ns": checkpoint_ns}).first()
            if not row:
                return None

            checkpoint_id = row[0]
            write_rows = conn.execute(text("""
                SELECT task_id, channel, serde_type, `blob`
                FROM crm_langgraph_checkpoint_writes
                WHERE thread_id = :thread_id
                  AND checkpoint_ns = :checkpoint_ns
                  AND checkpoint_id = :checkpoint_id
                ORDER BY task_id ASC, write_idx ASC
            """), {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            }).all()

        checkpoint: Checkpoint = self._load(row[2], row[3])
        checkpoint = {
            **checkpoint,
            "channel_values": self._load_blobs(thread_id, checkpoint_ns, checkpoint.get("channel_versions", {})),
        }
        parent_checkpoint_id = row[1]
        return CheckpointTuple(
            config=_config(thread_id, checkpoint_ns, checkpoint_id),
            checkpoint=checkpoint,
            metadata=self._load(row[4], row[5]),
            pending_writes=[
                (task_id, channel, self._load(serde_type, blob))
                for task_id, channel, serde_type, blob in write_rows
            ],
            parent_config=_config(thread_id, checkpoint_ns, parent_checkpoint_id) if parent_checkpoint_id else None,
        )

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        thread_id = config["configurable"]["thread_id"] if config else None
        checkpoint_ns = config["configurable"].get("checkpoint_ns") if config else None
        before_checkpoint_id = get_checkpoint_id(before) if before else None
        params: dict[str, Any] = {}
        clauses = []
        if thread_id:
            clauses.append("thread_id = :thread_id")
            params["thread_id"] = thread_id
        if checkpoint_ns is not None:
            clauses.append("checkpoint_ns = :checkpoint_ns")
            params["checkpoint_ns"] = checkpoint_ns
        if before_checkpoint_id:
            clauses.append("checkpoint_id < :before_checkpoint_id")
            params["before_checkpoint_id"] = before_checkpoint_id
        where_sql = "WHERE " + " AND ".join(clauses) if clauses else ""
        limit_sql = " LIMIT :limit" if limit is not None else ""
        if limit is not None:
            params["limit"] = limit
        with self.engine.begin() as conn:
            rows = conn.execute(text(f"""
                SELECT thread_id, checkpoint_ns, checkpoint_id
                FROM crm_langgraph_checkpoints
                {where_sql}
                ORDER BY thread_id ASC, checkpoint_ns ASC, checkpoint_id DESC
                {limit_sql}
            """), params).all()
        for row in rows:
            item = self.get_tuple(_config(row[0], row[1], row[2]))
            if not item:
                continue
            if filter and not all(item.metadata.get(key) == value for key, value in filter.items()):
                continue
            yield item

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        c = checkpoint.copy()
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = checkpoint["id"]
        parent_checkpoint_id = config["configurable"].get("checkpoint_id")
        resolved_metadata = get_checkpoint_metadata(config, metadata)
        _validate_checkpoint_persistence_contract(
            thread_id=thread_id,
            checkpoint_ns=checkpoint_ns,
            metadata=resolved_metadata,
        )
        values: dict[str, Any] = c.pop("channel_values", {})  # type: ignore[misc]
        checkpoint_type, checkpoint_blob = self._dump(c)
        metadata_type, metadata_blob = self._dump(resolved_metadata)
        with self.engine.begin() as conn:
            for channel, version in new_versions.items():
                serde_type, blob = self._dump(values[channel]) if channel in values else ("empty", b"")
                conn.execute(text("""
                    REPLACE INTO crm_langgraph_checkpoint_blobs
                        (thread_id, checkpoint_ns, channel, version, serde_type, `blob`)
                    VALUES
                        (:thread_id, :checkpoint_ns, :channel, :version, :serde_type, :blob)
                """), {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "channel": channel,
                    "version": _version_key(version),
                    "serde_type": serde_type,
                    "blob": blob,
                })
            conn.execute(text("""
                REPLACE INTO crm_langgraph_checkpoints
                    (thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id,
                     checkpoint_type, checkpoint_blob, metadata_type, metadata_blob)
                VALUES
                    (:thread_id, :checkpoint_ns, :checkpoint_id, :parent_checkpoint_id,
                     :checkpoint_type, :checkpoint_blob, :metadata_type, :metadata_blob)
            """), {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
                "parent_checkpoint_id": parent_checkpoint_id,
                "checkpoint_type": checkpoint_type,
                "checkpoint_blob": checkpoint_blob,
                "metadata_type": metadata_type,
                "metadata_blob": metadata_blob,
            })
        return _config(thread_id, checkpoint_ns, checkpoint_id)

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = config["configurable"]["checkpoint_id"]
        _validate_checkpoint_persistence_contract(
            thread_id=thread_id,
            checkpoint_ns=checkpoint_ns,
            metadata=get_checkpoint_metadata(config, {}),
        )
        insert_sql = "INSERT OR IGNORE" if self.engine.dialect.name == "sqlite" else "INSERT IGNORE"
        with self.engine.begin() as conn:
            for idx, (channel, value) in enumerate(writes):
                write_idx = WRITES_IDX_MAP.get(channel, idx)
                serde_type, blob = self._dump(value)
                conn.execute(text(f"""
                    {insert_sql} INTO crm_langgraph_checkpoint_writes
                        (thread_id, checkpoint_ns, checkpoint_id, task_id, write_idx,
                         task_path, channel, serde_type, `blob`)
                    VALUES
                        (:thread_id, :checkpoint_ns, :checkpoint_id, :task_id, :write_idx,
                         :task_path, :channel, :serde_type, :blob)
                """), {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": checkpoint_id,
                    "task_id": task_id,
                    "write_idx": write_idx,
                    "task_path": task_path,
                    "channel": channel,
                    "serde_type": serde_type,
                    "blob": blob,
                })

    def delete_thread(self, thread_id: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(text("DELETE FROM crm_langgraph_checkpoint_writes WHERE thread_id = :thread_id"), {"thread_id": thread_id})
            conn.execute(text("DELETE FROM crm_langgraph_checkpoint_blobs WHERE thread_id = :thread_id"), {"thread_id": thread_id})
            conn.execute(text("DELETE FROM crm_langgraph_checkpoints WHERE thread_id = :thread_id"), {"thread_id": thread_id})

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        return self.get_tuple(config)

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        for item in self.list(config, filter=filter, before=before, limit=limit):
            yield item

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        return self.put(config, checkpoint, metadata, new_versions)

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        self.put_writes(config, writes, task_id, task_path)

    async def adelete_thread(self, thread_id: str) -> None:
        self.delete_thread(thread_id)


customer_activity_checkpoint_saver = SQLAlchemyCheckpointSaver()
