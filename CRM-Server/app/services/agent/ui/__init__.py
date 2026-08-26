"""Single CRM Agent UI protocol."""

from app.services.agent.ui.schemas import (
    AgentChatInput,
    AgentChatRequest,
    AgentErrorCode,
    AgentTransportErrorEvent,
    AgentUIAction,
    AgentUIBlock,
    AgentUIEnvelope,
    AgentUIStreamEvent,
    InteractionBlock,
)

__all__ = [
    "AgentChatInput",
    "AgentChatRequest",
    "AgentErrorCode",
    "AgentTransportErrorEvent",
    "AgentUIAction",
    "AgentUIBlock",
    "AgentUIEnvelope",
    "AgentUIStreamEvent",
    "InteractionBlock",
]
