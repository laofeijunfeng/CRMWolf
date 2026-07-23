"""CRM AI Agent LangGraph state types."""
from typing import Any, Dict, List, Optional, TypedDict


class AgentGraphState(TypedDict, total=False):
    db: Any
    team_id: int
    user_id: int
    session_id: int
    content: str
    authorization: Optional[str]
    intent: Optional[str]
    parsed: Dict[str, Any]
    customer_candidates: List[Dict[str, Any]]
    response: Optional[str]
    events: List[Dict[str, Any]]
