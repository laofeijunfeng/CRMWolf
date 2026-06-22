"""
SSE Wrapper for LangGraph Stream Events

This module converts LangGraph astream_events output to CRMWolf SSE format,
ensuring frontend compatibility without any changes.

SSE Event Types (CRMWolf format):
- start: Session started
- node_start: Node execution started
- node_result: Node execution result
- tool_call: Tool call started
- tool_result: Tool execution result
- waiting_for_user: Human-in-the-Loop interrupt
- react_complete: ReAct loop completed
- workflow_complete: Workflow completed
- error: Error occurred

Usage:
    async for sse_event in stream_sse_events(app, inputs, thread_id):
        yield sse_event
"""

import json
from typing import Any, AsyncGenerator, Dict, List, Optional

from langchain_core.messages import BaseMessage
from langgraph.pregel import Pregel


# ==================== Custom JSON Encoder ====================


class SSEJsonEncoder(json.JSONEncoder):
    """
    Custom JSON encoder for SSE events that handles LangChain message objects.
    """

    def default(self, obj: Any) -> Any:
        """Convert LangChain messages to JSON-serializable dicts."""
        if isinstance(obj, BaseMessage):
            # Convert LangChain message to dict
            return {
                "type": obj.type,
                "content": obj.content,
                "additional_kwargs": obj.additional_kwargs,
            }
        # Fallback to default
        return super().default(obj)


# ==================== SSE Event Types ====================

SSE_EVENT_TYPES = {
    "START": "start",
    "NODE_START": "node_start",
    "NODE_RESULT": "node_result",
    "TOOL_CALL": "tool_call",
    "TOOL_RESULT": "tool_result",
    "WAITING_FOR_USER": "waiting_for_user",
    "REACT_COMPLETE": "react_complete",
    "WORKFLOW_COMPLETE": "workflow_complete",
    "ROUND_START": "round_start",
    "ROUND_COMPLETED": "round_completed",
    "ERROR": "error",
    "CONTENT": "content",
}


# ==================== SSE Event Builders ====================


def build_sse_event(event_type: str, data: Dict[str, Any]) -> str:
    """
    Build an SSE event string.

    Args:
        event_type: Event type name
        data: Event data dict

    Returns:
        SSE formatted string: "event: {type}\\ndata: {json}\\n\\n"
    """
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False, cls=SSEJsonEncoder)}\n\n"


def build_start_event(session_id: str) -> str:
    """Build session start event."""
    return build_sse_event(SSE_EVENT_TYPES["START"], {"session_id": session_id})


def build_node_start_event(node: str) -> str:
    """Build node start event."""
    return build_sse_event(SSE_EVENT_TYPES["NODE_START"], {"node": node})


def build_node_result_event(node: str, result: Dict[str, Any]) -> str:
    """Build node result event."""
    # Filter result for frontend display
    display_result = filter_result_for_display(result)
    return build_sse_event(SSE_EVENT_TYPES["NODE_RESULT"], {"node": node, "result": display_result})


def build_tool_call_event(tool: str, params: Optional[Dict[str, Any]] = None) -> str:
    """Build tool call event."""
    return build_sse_event(SSE_EVENT_TYPES["TOOL_CALL"], {"tool": tool, "params": params or {}})


def build_tool_result_event(tool: str, result: Dict[str, Any]) -> str:
    """Build tool result event."""
    display_result = filter_result_for_display(result)
    return build_sse_event(SSE_EVENT_TYPES["TOOL_RESULT"], {"tool": tool, "result": display_result})


def build_waiting_for_user_event(
    question: str,
    options: Optional[List[str]] = None,
    missing_fields: Optional[List[str]] = None,
    field_options: Optional[Dict[str, Any]] = None,
) -> str:
    """Build waiting for user event."""
    data = {
        "question": question,
        "options": options or [],
        "missing_fields": missing_fields or [],
        "field_options": field_options or {},
    }
    return build_sse_event(SSE_EVENT_TYPES["WAITING_FOR_USER"], data)


def build_react_complete_event(rounds: int, message: str) -> str:
    """Build ReAct complete event."""
    return build_sse_event(SSE_EVENT_TYPES["REACT_COMPLETE"], {"rounds": rounds, "message": message})


def build_workflow_complete_event(session_id: str, message: str, execution_summary: List[Dict[str, Any]]) -> str:
    """Build workflow complete event."""
    return build_sse_event(
        SSE_EVENT_TYPES["WORKFLOW_COMPLETE"],
        {"session_id": session_id, "message": message, "execution_summary": execution_summary},
    )


def build_error_event(message: str) -> str:
    """Build error event."""
    return build_sse_event(SSE_EVENT_TYPES["ERROR"], {"message": message})


def build_round_start_event(round: int) -> str:
    """Build round start event."""
    return build_sse_event(SSE_EVENT_TYPES["ROUND_START"], {"round": round})


def build_content_event(content: str) -> str:
    """Build content chunk event."""
    return build_sse_event(SSE_EVENT_TYPES["CONTENT"], {"content": content})


# ==================== Result Filter ====================


def filter_result_for_display(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Filter result dict for frontend display.

    Removes sensitive/internal fields and keeps display-friendly data.

    Args:
        result: Full result dict

    Returns:
        Filtered result dict
    """
    # Fields to exclude from display
    exclude_fields = {
        "db",
        "user",
        "session",
        "_internal",
        "raw_data",
    }

    filtered = {}
    for key, value in result.items():
        if key in exclude_fields:
            continue

        # Handle nested dicts
        if isinstance(value, dict):
            filtered[key] = filter_result_for_display(value)
        elif isinstance(value, list):
            # Filter list items if they are dicts
            filtered[key] = [
                filter_result_for_display(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            filtered[key] = value

    return filtered


# ==================== Main SSE Stream Function ====================


async def stream_sse_events(
    app: Pregel,
    inputs: Dict[str, Any],
    thread_id: str,
    config: Optional[Dict[str, Any]] = None,
) -> AsyncGenerator[str, None]:
    """
    Convert LangGraph stream to CRMWolf SSE format.

    Args:
        app: Compiled LangGraph application
        inputs: Input state dict
        thread_id: Thread/session ID
        config: Optional additional config

    Yields:
        SSE formatted event strings
    """
    # Build config with thread_id
    full_config = {
        "configurable": {
            "thread_id": thread_id,
        },
    }
    if config:
        full_config["configurable"].update(config.get("configurable", {}))

    # Yield start event
    yield build_start_event(thread_id)

    # Track execution state
    rounds = 0
    execution_history: List[Dict[str, Any]] = []
    current_node = None
    interrupted = False

    # Stream events
    try:
        async for event in app.astream_events(inputs, version="v2", config=full_config):
            event_type = event.get("event")
            event_name = event.get("name")
            event_data = event.get("data", {})

            # Handle different event types
            if event_type == "on_chain_start":
                # Node started
                current_node = event_name
                yield build_node_start_event(event_name)

            elif event_type == "on_chain_end":
                # Node completed
                output = event_data.get("output", {})
                # Skip routing functions (they return string route names)
                routing_strings = [
                    "workflow", "react", "end", "error",
                    "entity_resolver", "slot_collector", "preview",
                    "ambiguity_resolver", "ask_user", "confirm",
                    "execute", "rollback", "complete",
                ]
                if isinstance(output, str) and output in routing_strings:
                    # This is a routing decision, not a node result
                    continue
                # Also skip if output is not a dict (can't be filtered)
                if not isinstance(output, dict):
                    continue

                # ✅ NEW: Send content event if there's a reply_text or error
                # This ensures frontend receives content and can display messages
                if event_name == "intent_detector":
                    intent_result = output.get("intent_result")
                    if intent_result:
                        reply_text = intent_result.get("reply_text")
                        if reply_text:
                            yield build_content_event(reply_text)
                        # Also handle errors
                        if output.get("error"):
                            yield build_content_event(f"❌ {output['error']}")

                elif event_name == "entity_resolver":
                    # Handle entity resolution results
                    entity_result = output.get("entity_result")
                    if entity_result:
                        if entity_result.get("error"):
                            yield build_content_event(f"❌ {entity_result['error']}")
                    elif output.get("error"):
                        yield build_content_event(f"❌ {output['error']}")

                elif event_name == "slot_collector":
                    # Handle slot collection results
                    pending_missing_fields = output.get("pending_missing_fields")
                    if pending_missing_fields:
                        pending_question = output.get("pending_question", "请提供更多信息")
                        yield build_content_event(pending_question)

                elif event_name == "LangGraph":
                    # Final result - extract meaningful content for user
                    final_error = output.get("error")
                    if final_error:
                        yield build_content_event(f"❌ 处理失败：{final_error}")

                yield build_node_result_event(event_name, output)

                # Track execution history
                execution_history.append({
                    "node": event_name,
                    "output": filter_result_for_display(output),
                })

                # Check for round increment
                if event_name == "execute":
                    rounds += 1
                    yield build_round_start_event(rounds)

            elif event_type == "on_tool_start":
                # Tool call started
                tool_name = event_name
                tool_input = event_data.get("input", {})
                yield build_tool_call_event(tool_name, tool_input)

            elif event_type == "on_tool_end":
                # Tool completed
                tool_name = event_name
                tool_output = event_data.get("output", {})
                yield build_tool_result_event(tool_name, tool_output)

            elif event_type == "on_chat_model_stream":
                # LLM streaming content
                content_chunk = event_data.get("chunk", {})
                if content_chunk.get("content"):
                    yield build_content_event(content_chunk["content"])

            elif event_type == "on_interrupt":
                # Human-in-the-Loop interrupt
                interrupted = True
                interrupt_value = event_data.get("value", {})

                # Build waiting_for_user event with proper fields
                question = interrupt_value.get("question", "请提供更多信息")
                options = interrupt_value.get("options", [])
                missing_fields = interrupt_value.get("missing_fields", [])
                field_options = interrupt_value.get("field_options", {})

                yield build_waiting_for_user_event(question, options, missing_fields, field_options)

                # Stop streaming on interrupt
                return

        # Final event based on execution path
        if not interrupted:
            if "workflow_id" in inputs and inputs["workflow_id"]:
                # Workflow completed
                yield build_workflow_complete_event(
                    thread_id,
                    "流程执行完成",
                    execution_history,
                )
            else:
                # ReAct completed
                yield build_react_complete_event(rounds, "对话处理完成")

    except Exception as e:
        yield build_error_event(str(e))


# ==================== Resume Stream Function ====================


async def stream_resume_sse_events(
    app: Pregel,
    thread_id: str,
    user_response: str,
    config: Optional[Dict[str, Any]] = None,
) -> AsyncGenerator[str, None]:
    """
    Resume interrupted LangGraph stream with user response.

    Args:
        app: Compiled LangGraph application
        thread_id: Thread/session ID
        user_response: User's response to the pending question
        config: Optional additional config

    Yields:
        SSE formatted event strings
    """
    # Build config with thread_id
    full_config = {
        "configurable": {
            "thread_id": thread_id,
        },
    }
    if config:
        full_config["configurable"].update(config.get("configurable", {}))

    # Resume from interrupt
    yield build_start_event(thread_id)

    # Use update_state to resume (LangGraph pattern)
    # The Command(resume=user_response) pattern in the graph handles this

    try:
        async for event in app.astream_events(
            None,  # No new inputs, just resume
            version="v2",
            config=full_config,
        ):
            event_type = event.get("event")
            event_name = event.get("name")
            event_data = event.get("data", {})

            if event_type == "on_chain_start":
                yield build_node_start_event(event_name)

            elif event_type == "on_chain_end":
                output = event_data.get("output", {})
                yield build_node_result_event(event_name, output)

            elif event_type == "on_tool_start":
                tool_input = event_data.get("input", {})
                yield build_tool_call_event(event_name, tool_input)

            elif event_type == "on_tool_end":
                tool_output = event_data.get("output", {})
                yield build_tool_result_event(event_name, tool_output)

            elif event_type == "on_chat_model_stream":
                content_chunk = event_data.get("chunk", {})
                if content_chunk.get("content"):
                    yield build_content_event(content_chunk["content"])

            elif event_type == "on_interrupt":
                # Another interrupt during resume
                interrupt_value = event_data.get("value", {})
                yield build_waiting_for_user_event(
                    interrupt_value.get("question", ""),
                    interrupt_value.get("options", []),
                    interrupt_value.get("missing_fields", []),
                    interrupt_value.get("field_options", {}),
                )
                return

        yield build_react_complete_event(0, "对话继续完成")

    except Exception as e:
        yield build_error_event(str(e))