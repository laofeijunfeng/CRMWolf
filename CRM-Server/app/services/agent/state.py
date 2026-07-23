"""CRM AI Agent LangGraph state types."""
from typing import Any, Dict, List, Optional, TypedDict

from app.services.agent.schemas import AgentMemorySnapshot, AgentSemanticParseResult, AgentSuggestionResult


class AgentGraphState(TypedDict, total=False):
    db: Any
    team_id: int
    user_id: int
    session_id: int
    content: str
    authorization: Optional[str]
    intent: Optional[str]
    memory: AgentMemorySnapshot
    semantic_result: AgentSemanticParseResult
    semantic_metadata: Dict[str, Any]
    semantic_error: Optional[str]
    parsed: Dict[str, Any]
    customer_candidates: List[Dict[str, Any]]
    selected_customer: Dict[str, Any]
    business_context: Dict[str, Any]
    suggestion_result: AgentSuggestionResult
    suggestion_metadata: Dict[str, Any]
    suggestion_error: Optional[str]
    response: Optional[str]
    events: List[Dict[str, Any]]
