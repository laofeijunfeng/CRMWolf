"""CRM AI Agent LangGraph state types."""
from typing import Any, Dict, List, Optional, TypedDict


class AgentGraphState(TypedDict, total=False):
    team_id: int
    user_id: int
    session_id: int
    content: str
    intent: Optional[str]
    response: Optional[str]
    events: List[Dict[str, Any]]
