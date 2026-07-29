"""CRM AI Agent LangGraph state types."""
import operator
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from app.services.agent.schemas import (
    AgentFollowUpQualityResult,
    AgentMemorySnapshot,
    AgentSemanticParseResult,
    AgentSuggestionResult,
)


class AgentGraphState(TypedDict, total=False):
    db: Any
    team_id: int
    user_id: int
    session_id: int
    session_context: Dict[str, Any]
    content: str
    authorization: Optional[str]
    current_datetime: Any
    intent: Optional[str]
    memory: AgentMemorySnapshot
    semantic_result: AgentSemanticParseResult
    semantic_metadata: Dict[str, Any]
    semantic_error: Optional[str]
    follow_up_quality_result: AgentFollowUpQualityResult
    follow_up_quality_metadata: Dict[str, Any]
    follow_up_quality_error: Optional[str]
    parsed: Dict[str, Any]
    customer_candidates: List[Dict[str, Any]]
    creation_duplicate_candidates: Dict[str, Any]
    selected_customer: Dict[str, Any]
    business_context: Dict[str, Any]
    suggestion_result: AgentSuggestionResult
    suggestion_metadata: Dict[str, Any]
    suggestion_error: Optional[str]
    response: Optional[str]
    events: List[Dict[str, Any]]


class PendingTaskGraphState(TypedDict, total=False):
    db: Any
    session: Any
    task: Any
    suspended_candidates: List[Dict[str, Any]]
    turn_relation_decision: Any
    resumed_task: Any
    turn_input: Any
    content: str
    team_id: int
    user_id: int
    session_id: int
    authorization: Optional[str]
    handled: bool
    assistant_content: Optional[str]
    switch_notice: Optional[str]
    suspended_task: Any
    suspend_reason: Optional[str]
    selected_customer: Dict[str, Any]
    remember_pending_task: bool
    clear_pending_task_id: Optional[int]
    confirmation_decision: Any
    preflight_result: Any
    interaction_result: Any
    events: Annotated[List[Dict[str, Any]], operator.add]
