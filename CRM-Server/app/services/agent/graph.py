"""CRM AI Agent LangGraph service.

The graph intentionally starts small: it only classifies the user message and
returns streamable Agent events. CRM business writes will be added as tool
nodes that call existing backend APIs.
"""
from typing import Any, AsyncGenerator, Dict

from langgraph.graph import END, START, StateGraph

from app.services.agent.state import AgentGraphState


class CRMAgentGraphService:
    def __init__(self) -> None:
        self._graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(AgentGraphState)
        graph.add_node("classify_intent", self._classify_intent)
        graph.add_node("build_response", self._build_response)
        graph.add_edge(START, "classify_intent")
        graph.add_edge("classify_intent", "build_response")
        graph.add_edge("build_response", END)
        return graph.compile()

    def _classify_intent(self, state: AgentGraphState) -> AgentGraphState:
        content = state.get("content", "")
        intent = "GENERAL"

        if "回款" in content or "到账" in content or "打款" in content:
            intent = "PAYMENT_RECORD"
        elif "联系人" in content:
            intent = "CREATE_CONTACT"
        elif "跟进" in content or "沟通" in content or "客户" in content:
            intent = "CUSTOMER_FOLLOW_UP"

        return {"intent": intent}

    def _build_response(self, state: AgentGraphState) -> AgentGraphState:
        intent = state.get("intent") or "GENERAL"
        response_by_intent = {
            "CUSTOMER_FOLLOW_UP": (
                "已识别为客户跟进场景。下一阶段会接入客户识别和跟进记录创建 Tool。"
            ),
            "PAYMENT_RECORD": (
                "已识别为回款场景。下一阶段会接入合同、回款计划和回款登记 Tool。"
            ),
            "CREATE_CONTACT": (
                "已识别为联系人维护场景。下一阶段会接入客户匹配和联系人创建 Tool。"
            ),
            "GENERAL": "已收到消息。下一阶段会接入更完整的 CRM Agent 意图识别。",
        }
        response = response_by_intent[intent]
        events = [
            {"event": "intent", "intent": intent},
            {
                "event": "final",
                "intent": intent,
                "content": response,
                "tool_execution_enabled": False,
            },
        ]
        return {"response": response, "events": events}

    async def run(self, input_state: AgentGraphState) -> AgentGraphState:
        result: Dict[str, Any] = await self._graph.ainvoke(input_state)
        return result

    async def stream_events(self, input_state: AgentGraphState) -> AsyncGenerator[Dict[str, Any], None]:
        result = await self.run(input_state)
        for event in result.get("events", []):
            yield event


crm_agent_graph_service = CRMAgentGraphService()
