"""CRM AI Agent LangGraph service."""
import re
from typing import Any, AsyncGenerator, Dict, List, Optional

from langgraph.graph import END, START, StateGraph

from app.services.agent.state import AgentGraphState
from app.services.agent.tools import CRMAgentToolService
from app.services.agent.tools.base import AgentToolContext


class CRMAgentGraphService:
    def __init__(self, tool_service: Optional[CRMAgentToolService] = None) -> None:
        self.tool_service = tool_service or CRMAgentToolService()
        self._graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(AgentGraphState)
        graph.add_node("classify_intent", self._classify_intent)
        graph.add_node("parse_message", self._parse_message)
        graph.add_node("search_customer", self._search_customer)
        graph.add_node("build_response", self._build_response)
        graph.add_edge(START, "classify_intent")
        graph.add_edge("classify_intent", "parse_message")
        graph.add_edge("parse_message", "search_customer")
        graph.add_edge("search_customer", "build_response")
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

    def _parse_message(self, state: AgentGraphState) -> AgentGraphState:
        content = state.get("content", "")
        intent = state.get("intent") or "GENERAL"
        customer_name = self._extract_customer_name(content, intent)
        next_follow_time = self._extract_next_follow_time(content)
        next_action = self._extract_next_action(content, next_follow_time)
        parsed = {
            "customer_name": customer_name,
            "follow_up_content": content,
            "next_action": next_action,
            "next_follow_time_text": next_follow_time,
        }
        return {
            "parsed": parsed,
            "events": [{"event": "entity_parse", "intent": intent, "parsed": parsed}],
        }

    async def _search_customer(self, state: AgentGraphState) -> AgentGraphState:
        parsed = state.get("parsed") or {}
        customer_name = parsed.get("customer_name")
        if not customer_name or not state.get("authorization") or not state.get("db"):
            return {}

        context = AgentToolContext(
            db=state["db"],
            team_id=state["team_id"],
            user_id=state["user_id"],
            session_id=state["session_id"],
            authorization=state["authorization"],
        )
        result = await self.tool_service.search_customers(context, customer_name, limit=10)
        events = [result.to_event()]
        candidates = self._extract_customer_candidates(result.data) if result.success else []
        if candidates:
            events.append({"event": "customer_candidates", "customers": candidates})
        return {"customer_candidates": candidates, "events": events}

    def _build_response(self, state: AgentGraphState) -> AgentGraphState:
        intent = state.get("intent") or "GENERAL"
        parsed = state.get("parsed") or {}
        candidates = state.get("customer_candidates") or []
        events = [{"event": "intent", "intent": intent}]

        if state.get("events"):
            events.extend(state["events"])

        response, action = self._build_business_response(intent, parsed, candidates)
        if action:
            events.append({"event": "confirmation_required", **action})
        events.append({
            "event": "final",
            "intent": intent,
            "content": response,
            "tool_execution_enabled": False,
        })
        return {"response": response, "events": events}

    async def run(self, input_state: AgentGraphState) -> AgentGraphState:
        result: Dict[str, Any] = await self._graph.ainvoke(input_state)
        return result

    async def stream_events(self, input_state: AgentGraphState) -> AsyncGenerator[Dict[str, Any], None]:
        result = await self.run(input_state)
        for event in result.get("events", []):
            yield event

    @staticmethod
    def _extract_customer_name(content: str, intent: str) -> Optional[str]:
        patterns = [
            r"和(?P<name>.+?)的[^，,。；;]*?(?:沟通|聊|交流|确认)",
            r"给(?P<name>.+?)(?:创建|新增|加).*?联系人",
            r"(?P<name>[\u4e00-\u9fa5A-Za-z0-9（）()·]{2,30}?)(?:今天|已|刚刚|昨日|昨天)?.*?(?:回款|到账|打款)",
        ]
        for pattern in patterns:
            match = re.search(pattern, content)
            if match:
                name = match.group("name").strip(" ，,。；;")
                return name or None
        if intent == "CUSTOMER_FOLLOW_UP":
            match = re.search(r"([\u4e00-\u9fa5A-Za-z0-9（）()·]{2,30}?)(?:项目|客户|王总|李总|张总)", content)
            if match:
                return match.group(1).strip(" ，,。；;")
        return None

    @staticmethod
    def _extract_next_follow_time(content: str) -> Optional[str]:
        match = re.search(r"(下周[一二三四五六日天]|明天|后天|下个月|月底|周[一二三四五六日天])", content)
        return match.group(1) if match else None

    @staticmethod
    def _extract_next_action(content: str, next_follow_time: Optional[str]) -> Optional[str]:
        if not next_follow_time:
            return None
        start = content.find(next_follow_time)
        if start < 0:
            return None
        action = content[start:].strip(" ，,。；;")
        return action or None

    @staticmethod
    def _extract_customer_candidates(data: Any) -> List[Dict[str, Any]]:
        if not isinstance(data, dict):
            return []
        items = data.get("items") or []
        candidates = []
        for item in items[:10]:
            if not isinstance(item, dict):
                continue
            candidates.append({
                "id": item.get("id"),
                "account_name": item.get("account_name"),
                "owner_info": item.get("owner_info"),
                "collaborator_infos": item.get("collaborator_infos") or [],
            })
        return candidates

    @staticmethod
    def _build_business_response(intent: str, parsed: Dict[str, Any], candidates: List[Dict[str, Any]]):
        customer_name = parsed.get("customer_name")
        if intent == "CUSTOMER_FOLLOW_UP":
            if not customer_name:
                return "我识别到这是客户跟进，但还缺少明确客户名称。请补充客户名称。", None
            if len(candidates) == 1:
                customer = candidates[0]
                return (
                    f"我识别到客户「{customer.get('account_name')}」的跟进记录。"
                    "请确认是否创建这条跟进记录？"
                ), {
                    "action": "create_customer_follow_up",
                    "customer": customer,
                    "payload": {
                        "customer_id": customer.get("id"),
                        "content": parsed.get("follow_up_content"),
                        "next_action": parsed.get("next_action"),
                        "next_follow_time_text": parsed.get("next_follow_time_text"),
                    },
                }
            if len(candidates) > 1:
                return f"我找到了多个可能的客户，请先确认要记录到哪一个客户：{customer_name}", None
            return f"我识别到客户「{customer_name}」，但当前没有搜索到可访问的客户。请确认客户名称是否正确。", None

        if intent == "PAYMENT_RECORD":
            if not customer_name:
                return "我识别到这是回款场景，但还缺少明确客户名称。请补充客户名称。", None
            return f"我识别到「{customer_name}」的回款信息。下一步需要确认合同和回款计划后再登记回款。", None

        if intent == "CREATE_CONTACT":
            if not customer_name:
                return "我识别到这是创建联系人，但还缺少明确客户名称。请补充客户名称。", None
            return f"我识别到要为「{customer_name}」创建联系人。下一步需要确认联系人手机号、职务等必填信息。", None

        return "已收到消息。当前 Agent 优先处理客户跟进、联系人维护和回款登记场景。", None


crm_agent_graph_service = CRMAgentGraphService()
