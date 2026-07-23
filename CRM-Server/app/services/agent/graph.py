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

        if "发票抬头" in content or "开票抬头" in content:
            intent = "CREATE_INVOICE_TITLE"
        elif "回款" in content or "到账" in content or "打款" in content:
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
        contact = self.parse_contact_fields_from_text(content) if intent == "CREATE_CONTACT" else {}
        invoice_title = self.parse_invoice_title_fields_from_text(content) if intent == "CREATE_INVOICE_TITLE" else {}
        next_follow_time = self._extract_next_follow_time(content)
        next_action = self._extract_next_action(content, next_follow_time)
        parsed = {
            "customer_name": customer_name,
            "follow_up_content": content,
            "contact": contact,
            "missing_contact_fields": self.missing_contact_fields(contact) if intent == "CREATE_CONTACT" else [],
            "invoice_title": invoice_title,
            "missing_invoice_title_fields": (
                self.missing_invoice_title_fields(invoice_title) if intent == "CREATE_INVOICE_TITLE" else []
            ),
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
            event_name = "confirmation_required"
            if action.get("action") in {
                "select_customer_for_follow_up",
                "select_customer_for_contact",
                "select_customer_for_invoice_title",
            }:
                event_name = "customer_selection_required"
            elif action.get("action") == "collect_contact_fields":
                event_name = "contact_fields_required"
            elif action.get("action") == "collect_invoice_title_fields":
                event_name = "invoice_title_fields_required"
            events.append({"event": event_name, **action})
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
            r"给(?P<name>.+?)(?:创建|新增|添加).*?(?:发票抬头|开票抬头)",
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
                candidate_lines = [
                    f"{index}. {customer.get('account_name')}"
                    for index, customer in enumerate(candidates, start=1)
                ]
                return (
                    "我找到了多个可能的客户，请回复序号或客户名称确认要记录到哪一个客户："
                    + "；".join(candidate_lines)
                ), {
                    "action": "select_customer_for_follow_up",
                    "customers": candidates,
                    "payload": {
                        "content": parsed.get("follow_up_content"),
                        "next_action": parsed.get("next_action"),
                        "next_follow_time_text": parsed.get("next_follow_time_text"),
                    },
                }
            return f"我识别到客户「{customer_name}」，但当前没有搜索到可访问的客户。请确认客户名称是否正确。", None

        if intent == "PAYMENT_RECORD":
            if not customer_name:
                return "我识别到这是回款场景，但还缺少明确客户名称。请补充客户名称。", None
            return f"我识别到「{customer_name}」的回款信息。下一步需要确认合同和回款计划后再登记回款。", None

        if intent == "CREATE_CONTACT":
            if not customer_name:
                return "我识别到这是创建联系人，但还缺少明确客户名称。请补充客户名称。", None
            contact = parsed.get("contact") or {}
            missing_fields = CRMAgentGraphService.missing_contact_fields(contact)
            if len(candidates) == 1:
                customer = candidates[0]
                if missing_fields:
                    return (
                        f"我识别到要为「{customer.get('account_name')}」创建联系人，"
                        f"还需要补充：{CRMAgentGraphService.format_contact_missing_fields(missing_fields)}。"
                    ), {
                        "action": "collect_contact_fields",
                        "customer": customer,
                        "payload": {
                            "customer_id": customer.get("id"),
                            "contact": contact,
                            "missing_fields": missing_fields,
                        },
                    }
                return (
                    f"我识别到要为「{customer.get('account_name')}」创建联系人「{contact.get('name')}」。"
                    "请确认是否创建？"
                ), {
                    "action": "create_contact",
                    "customer": customer,
                    "payload": {
                        "customer_id": customer.get("id"),
                        "contact": contact,
                    },
                }
            if len(candidates) > 1:
                candidate_lines = [
                    f"{index}. {customer.get('account_name')}"
                    for index, customer in enumerate(candidates, start=1)
                ]
                return (
                    "我找到了多个可能的客户，请回复序号或客户名称确认要把联系人创建到哪一个客户："
                    + "；".join(candidate_lines)
                ), {
                    "action": "select_customer_for_contact",
                    "customers": candidates,
                    "payload": {
                        "contact": contact,
                        "missing_fields": missing_fields,
                    },
                }
            return f"我识别到要为「{customer_name}」创建联系人，但当前没有搜索到可访问的客户。请确认客户名称是否正确。", None

        if intent == "CREATE_INVOICE_TITLE":
            if not customer_name:
                return "我识别到这是创建发票抬头，但还缺少明确客户名称。请补充客户名称。", None
            invoice_title = parsed.get("invoice_title") or {}
            missing_fields = CRMAgentGraphService.missing_invoice_title_fields(invoice_title)
            if len(candidates) == 1:
                customer = candidates[0]
                set_default = bool(invoice_title.pop("set_default", False))
                if missing_fields:
                    return (
                        f"我识别到要为「{customer.get('account_name')}」创建发票抬头，"
                        f"还需要补充：{CRMAgentGraphService.format_invoice_title_missing_fields(missing_fields)}。"
                    ), {
                        "action": "collect_invoice_title_fields",
                        "customer": customer,
                        "payload": {
                            "customer_id": customer.get("id"),
                            "invoice_title": invoice_title,
                            "missing_fields": missing_fields,
                            "set_default": set_default,
                        },
                    }
                return (
                    f"我识别到要为「{customer.get('account_name')}」创建发票抬头「{invoice_title.get('title')}」。"
                    "请确认是否创建？"
                ), {
                    "action": "create_invoice_title",
                    "customer": customer,
                    "payload": {
                        "customer_id": customer.get("id"),
                        "invoice_title": invoice_title,
                        "set_default": set_default,
                    },
                }
            if len(candidates) > 1:
                candidate_lines = [
                    f"{index}. {customer.get('account_name')}"
                    for index, customer in enumerate(candidates, start=1)
                ]
                set_default = bool(invoice_title.pop("set_default", False))
                return (
                    "我找到了多个可能的客户，请回复序号或客户名称确认要把发票抬头创建到哪一个客户："
                    + "；".join(candidate_lines)
                ), {
                    "action": "select_customer_for_invoice_title",
                    "customers": candidates,
                    "payload": {
                        "invoice_title": invoice_title,
                        "missing_fields": missing_fields,
                        "set_default": set_default,
                    },
                }
            return f"我识别到要为「{customer_name}」创建发票抬头，但当前没有搜索到可访问的客户。请确认客户名称是否正确。", None

        return "已收到消息。当前 Agent 优先处理客户跟进、联系人维护、发票抬头和回款登记场景。", None

    @staticmethod
    def parse_contact_fields_from_text(content: str) -> Dict[str, Any]:
        contact: Dict[str, Any] = {"is_decision_maker": False}
        name_match = re.search(
            r"联系人(?P<name>[\u4e00-\u9fa5A-Za-z·]{2,20})(?:，|,|。|；|;|\s|$)",
            content,
        )
        if name_match:
            contact["name"] = name_match.group("name").strip()

        mobile_match = re.search(r"1[3-9]\d{9}", content)
        if mobile_match:
            contact["mobile"] = mobile_match.group(0)

        position_match = re.search(r"(?:职务|职位|岗位)[:：是为\s]*(?P<position>[^，,。；;\s]+)", content)
        if position_match:
            contact["position"] = position_match.group("position").strip()

        if re.search(r"未知|不清楚|不确定", content):
            contact["gender"] = "0"
        elif re.search(r"女士|女性|女\b", content):
            contact["gender"] = "2"
        elif re.search(r"先生|男性|男\b", content):
            contact["gender"] = "1"

        if re.search(r"决策人|关键人|关键决策", content):
            contact["is_decision_maker"] = True

        email_match = re.search(r"[\w.\-+]+@[\w.\-]+\.\w+", content)
        if email_match:
            contact["email"] = email_match.group(0)

        return {key: value for key, value in contact.items() if value not in (None, "")}

    @staticmethod
    def missing_contact_fields(contact: Dict[str, Any]) -> List[str]:
        required_fields = ["name", "mobile", "position", "gender"]
        return [field for field in required_fields if not contact.get(field)]

    @staticmethod
    def format_contact_missing_fields(fields: List[str]) -> str:
        labels = {
            "name": "联系人姓名",
            "mobile": "手机号",
            "position": "职务",
            "gender": "性别（男/女/未知）",
        }
        return "、".join(labels.get(field, field) for field in fields)

    @staticmethod
    def parse_invoice_title_fields_from_text(content: str) -> Dict[str, Any]:
        invoice_title: Dict[str, Any] = {
            "title_type": "PERSONAL" if re.search(r"个人(?:发票|抬头|开票抬头)", content) else "COMPANY",
        }

        title_patterns = [
            r"(?:抬头|发票抬头|开票抬头)(?:是|为|[:：])(?P<title>[^，,。；;]+)",
            r"(?:创建|新增|添加)(?:发票抬头|开票抬头)(?P<title>[^，,。；;]+)",
        ]
        for pattern in title_patterns:
            match = re.search(pattern, content)
            if match:
                invoice_title["title"] = match.group("title").strip()
                break

        field_patterns = {
            "taxpayer_id": r"(?:税号|纳税人识别号)(?:是|为|[:：])?(?P<value>[A-Za-z0-9]{8,30})",
            "bank_name": r"(?:开户行)(?:是|为|[:：])(?P<value>[^，,。；;]+)",
            "bank_account": r"(?:开户账号|银行账号|账号)(?:是|为|[:：])(?P<value>[A-Za-z0-9\- ]{6,40})",
            "address": r"(?:开票地址|地址)(?:是|为|[:：])(?P<value>[^，,。；;]+)",
            "phone": r"(?:开票电话|电话)(?:是|为|[:：])(?P<value>[0-9\- ]{6,30})",
        }
        for field, pattern in field_patterns.items():
            match = re.search(pattern, content)
            if match:
                invoice_title[field] = match.group("value").strip()

        if re.search(r"默认|设为默认|设置默认", content):
            invoice_title["set_default"] = True

        return {key: value for key, value in invoice_title.items() if value not in (None, "")}

    @staticmethod
    def missing_invoice_title_fields(invoice_title: Dict[str, Any]) -> List[str]:
        required_fields = ["title_type", "title", "taxpayer_id"]
        return [field for field in required_fields if not invoice_title.get(field)]

    @staticmethod
    def format_invoice_title_missing_fields(fields: List[str]) -> str:
        labels = {
            "title_type": "抬头类型（单位/个人）",
            "title": "开票抬头",
            "taxpayer_id": "纳税人识别号",
        }
        return "、".join(labels.get(field, field) for field in fields)


crm_agent_graph_service = CRMAgentGraphService()
