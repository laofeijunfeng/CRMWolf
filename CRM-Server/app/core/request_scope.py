"""Request-scoped authorization limits for internal Agent workers."""

from contextvars import ContextVar

agent_worker_permissions: ContextVar[frozenset[str] | None] = ContextVar(
    "agent_worker_permissions",
    default=None,
)

agent_worker_execution_id: ContextVar[str | None] = ContextVar(
    "agent_worker_execution_id",
    default=None,
)
