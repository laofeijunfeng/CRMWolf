"""
AgentState Definition for LangGraph AI Assistant

This module defines the complete state structure for the LangGraph agent graph.
The state must be JSON-serializable for Redis checkpoint persistence.

Note: db and user runtime references are passed through config["configurable"],
not stored in the state.
"""

from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langgraph.graph import add_messages


class AgentState(TypedDict):
    """
    Complete state structure for CRMWolf AI Assistant LangGraph.

    All fields must be JSON-serializable for Redis Checkpointer persistence.
    Runtime references (db, user) are passed through config["configurable"].

    Messages field uses LangGraph's add_messages reducer for automatic merging.
    """

    # ==================== Message History ====================
    # OpenAI-compatible message format, automatically merged by add_messages
    messages: Annotated[List[Dict[str, Any]], add_messages]

    # ==================== Session Context ====================
    # Unique session identifier for this conversation
    session_id: str

    # User and team identifiers (required for team_id isolation)
    user_id: int
    team_id: int

    # ==================== Entity Context ====================
    # Current focused entity from user interaction
    # Example: {"entity_type": "customer", "entity_id": 101, "entity_name": "张三科技"}
    entity_context: Optional[Dict[str, Any]]

    # ==================== Execution State ====================
    # ReAct loop round counter
    round_num: int

    # History of executed tools/actions for audit trail
    # Example: [{"tool": "create_customer", "params": {...}, "result": {...}, "timestamp": "..."}]
    execution_history: List[Dict[str, Any]]

    # Recently mentioned/created entities for shortcut resolution
    # Example: {"customer_id": 101, "lead_id": 205}
    recent_entities: Dict[str, int]

    # ==================== Intent Detection Result ====================
    # Result from IntentDetectorNode
    # Example: {"action_id": "create_customer", "entity_type": "customer", "entity_hint": "张三"}
    intent_result: Optional[Dict[str, Any]]

    # ==================== Entity Resolution Result ====================
    # Result from EntityResolverNode
    # Example: {"entity_id": 101, "confidence": 0.90, "matched_by": "exact_norm"}
    # Or: {"candidates": [...], "confidence": 0.50} for disambiguation
    entity_result: Optional[Dict[str, Any]]

    # ==================== Preview Result ====================
    # Result from PreviewNode (ActionEntry.preview call)
    # Contains the preview snapshot for user confirmation
    preview_result: Optional[Dict[str, Any]]

    # ==================== Execution Result ====================
    # Result from ExecuteNode (ActionEntry.execute call)
    # Contains the actual execution outcome
    exec_result: Optional[Dict[str, Any]]

    # ==================== Human-in-the-Loop ====================
    # Flag indicating the graph is paused waiting for user input
    waiting_for_user: bool

    # Question to ask the user
    pending_question: Optional[str]

    # Options for user to choose (for select-type questions)
    pending_options: Optional[List[str]]

    # Missing fields that need user input
    # Example: ["contact_phone", "customer_source"]
    pending_missing_fields: Optional[List[str]]

    # Field options for dropdown/autocomplete
    # Example: {"customer_source": ["线上咨询", "电话咨询", "转介绍"]}
    pending_field_options: Optional[Dict[str, Any]]

    # ==================== Workflow Flow Control ====================
    # Workflow ID if matched (None for ReAct mode)
    workflow_id: Optional[str]

    # Current step index in the workflow
    workflow_step_index: int

    # Rollback points for error recovery
    # Each point contains: step_id, snapshot, timestamp, checkpoint_id
    rollback_points: List[Dict[str, Any]]

    # ==================== Error State ====================
    # Error message if something went wrong
    error: Optional[str]

    # Flag indicating workflow was terminated
    workflow_terminated: bool

    # Reason for termination (guardrails_block, user_cancel, max_rounds_reached)
    termination_reason: Optional[str]


class UserExecCtx(TypedDict):
    """
    User execution context for ActionEntry calls.
    Passed through config["configurable"], not stored in state.

    Used for:
    - team_id isolation (required for all CRUD operations)
    - Audit trail (source and is_ai fields)
    - Permission checks (user_id)
    """

    user_id: int
    team_id: int
    source: str  # "ai_assistant"
    is_ai: bool  # True for AI-initiated actions


class RollbackPoint(TypedDict):
    """
    Structure for a rollback point in workflow execution.

    Stored in AgentState.rollback_points list.
    """

    # Step ID where the rollback point was created
    step_id: str

    # Snapshot of the state at this point
    snapshot: Dict[str, Any]

    # Timestamp when the rollback point was created
    timestamp: str

    # LangGraph checkpoint ID for precise state restoration
    checkpoint_id: Optional[str]


class EntityCandidate(TypedDict):
    """
    Entity candidate for disambiguation.

    Returned by EntityResolver when multiple matches are found.
    """

    id: int
    name: str
    hint: str  # Differentiating hint (e.g., "最近跟进 5/20")
    matched_by: str  # "exact_norm" | "prefix_norm" | "wide" | "raw"
    entity_type: str


# ==================== Helper Functions ====================


def create_initial_state(
    session_id: str,
    user_id: int,
    team_id: int,
    user_message: str,
    entity_context: Optional[Dict[str, Any]] = None,
) -> AgentState:
    """
    Create an initial AgentState for a new conversation.

    Args:
        session_id: Unique session identifier
        user_id: User ID from authentication
        team_id: Team ID for isolation
        user_message: Initial user message
        entity_context: Optional entity context from previous interaction

    Returns:
        Initial AgentState with all required fields set
    """
    return AgentState(
        messages=[{"role": "user", "content": user_message}],
        session_id=session_id,
        user_id=user_id,
        team_id=team_id,
        entity_context=entity_context,
        round_num=0,
        execution_history=[],
        recent_entities={},
        intent_result=None,
        entity_result=None,
        preview_result=None,
        exec_result=None,
        waiting_for_user=False,
        pending_question=None,
        pending_options=None,
        pending_missing_fields=None,
        pending_field_options=None,
        workflow_id=None,
        workflow_step_index=0,
        rollback_points=[],
        error=None,
        workflow_terminated=False,
        termination_reason=None,
    )


def update_state_with_entity(state: AgentState, entity_type: str, entity_id: int, entity_name: str) -> AgentState:
    """
    Update state with a newly resolved or created entity.

    Updates both entity_context and recent_entities for future shortcut resolution.

    Args:
        state: Current AgentState
        entity_type: Entity type (customer, lead, opportunity, etc.)
        entity_id: Entity ID
        entity_name: Entity name for display

    Returns:
        Updated AgentState
    """
    new_entity_context = {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "entity_name": entity_name,
    }

    new_recent_entities = {
        **state.get("recent_entities", {}),
        f"{entity_type}_id": entity_id,
    }

    return {
        **state,
        "entity_context": new_entity_context,
        "recent_entities": new_recent_entities,
    }