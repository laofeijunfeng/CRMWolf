"""CRM AI Agent LangGraph service."""
from __future__ import annotations

from typing import Any, AsyncGenerator, Dict, List, Optional

from langgraph.graph import END, START, StateGraph

from app.services.agent.memory import AgentMemoryService, agent_memory_service
from app.services.agent.schemas import AgentSemanticParseResult
from app.services.agent.semantic import AgentSemanticParser, AgentSemanticParserError, agent_semantic_parser
from app.services.agent.state import AgentGraphState
from app.services.agent.suggestion import (
    AgentSuggestionGenerator,
    AgentSuggestionGeneratorError,
    agent_suggestion_generator,
)
from app.services.agent.temporal import AgentTemporalResolver, agent_temporal_resolver
from app.services.agent.tool_registry import AgentToolRegistry, agent_tool_registry
from app.services.agent.tools import CRMAgentToolService
from app.services.agent.tools.base import AgentToolContext


class CRMAgentGraphService:
    def __init__(
        self,
        tool_service: Optional[CRMAgentToolService] = None,
        semantic_parser: Optional[AgentSemanticParser] = None,
        memory_service: Optional[AgentMemoryService] = None,
        tool_registry: Optional[AgentToolRegistry] = None,
        temporal_resolver: Optional[AgentTemporalResolver] = None,
        suggestion_generator: Optional[AgentSuggestionGenerator] = None,
    ) -> None:
        self.semantic_parser = semantic_parser or agent_semantic_parser
        self.memory_service = memory_service or agent_memory_service
        self.temporal_resolver = temporal_resolver or agent_temporal_resolver
        self.suggestion_generator = suggestion_generator or agent_suggestion_generator
        if tool_registry:
            self.tool_registry = tool_registry
        elif tool_service:
            self.tool_registry = AgentToolRegistry(tool_service)
        else:
            self.tool_registry = agent_tool_registry
        self._graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(AgentGraphState)
        graph.add_node("load_memory", self._load_memory)
        graph.add_node("semantic_parse", self._semantic_parse)
        graph.add_node("search_customer", self._search_customer)
        graph.add_node("load_customer_context", self._load_customer_context)
        graph.add_node("generate_suggestions", self._generate_suggestions)
        graph.add_node("build_response", self._build_response)
        graph.add_edge(START, "load_memory")
        graph.add_edge("load_memory", "semantic_parse")
        graph.add_edge("semantic_parse", "search_customer")
        graph.add_edge("search_customer", "load_customer_context")
        graph.add_edge("load_customer_context", "generate_suggestions")
        graph.add_edge("generate_suggestions", "build_response")
        graph.add_edge("build_response", END)
        return graph.compile()

    def _load_memory(self, state: AgentGraphState) -> AgentGraphState:
        db = state.get("db")
        if not db:
            return {}
        memory = self.memory_service.load_snapshot(
            db,
            team_id=state["team_id"],
            user_id=state["user_id"],
            session_id=state["session_id"],
        )
        return {
            "memory": memory,
            "events": [{"event": "memory_loaded"}],
        }

    async def _semantic_parse(self, state: AgentGraphState) -> AgentGraphState:
        try:
            if hasattr(self.semantic_parser, "parse_with_metadata"):
                envelope = await self.semantic_parser.parse_with_metadata(
                    state["db"],
                    team_id=state["team_id"],
                    user_message=state.get("content", ""),
                    memory=state.get("memory"),
                )
                semantic_result = envelope.result
                parse_source = envelope.parse_source
                model_name = envelope.model
            else:
                semantic_result = await self.semantic_parser.parse(
                    state["db"],
                    team_id=state["team_id"],
                    user_message=state.get("content", ""),
                    memory=state.get("memory"),
                )
                parse_source = "test_parser"
                model_name = None
        except AgentSemanticParserError as exc:
            return {
                "intent": "UNKNOWN",
                "semantic_error": str(exc),
                "events": [{"event": "semantic_parse_failed", "message": str(exc)}],
            }

        parsed = self._parsed_from_semantic(semantic_result, state.get("content", ""))
        return {
            "intent": semantic_result.intent,
            "semantic_result": semantic_result,
            "semantic_metadata": {
                "parse_source": parse_source,
                "model": model_name,
            },
            "parsed": parsed,
        }

    async def _search_customer(self, state: AgentGraphState) -> AgentGraphState:
        semantic_result = state.get("semantic_result")
        parsed = state.get("parsed") or {}
        customer_name = parsed.get("customer_name")
        if (
            not customer_name
            or not state.get("authorization")
            or not state.get("db")
            or self._requires_clarification(semantic_result)
        ):
            return {}

        context = AgentToolContext(
            db=state["db"],
            team_id=state["team_id"],
            user_id=state["user_id"],
            session_id=state["session_id"],
            authorization=state["authorization"],
        )
        result = await self.tool_registry.execute(
            "search_customers",
            context,
            {"keyword": customer_name, "limit": 10},
        )
        events = [result.to_event()]
        candidates = self._extract_customer_candidates(result.data) if result.success else []
        if candidates:
            events.append({"event": "customer_candidates", "customers": candidates})
        state_update: AgentGraphState = {"customer_candidates": candidates, "events": events}
        if len(candidates) == 1:
            state_update["selected_customer"] = candidates[0]
        return state_update

    async def _load_customer_context(self, state: AgentGraphState) -> AgentGraphState:
        customer = state.get("selected_customer") or {}
        customer_id = customer.get("id")
        if (
            not customer_id
            or not state.get("authorization")
            or not state.get("db")
            or self._requires_clarification(state.get("semantic_result"))
        ):
            return {}

        context = AgentToolContext(
            db=state["db"],
            team_id=state["team_id"],
            user_id=state["user_id"],
            session_id=state["session_id"],
            authorization=state["authorization"],
        )
        result = await self.tool_registry.execute(
            "get_customer_context",
            context,
            {"customer_id": customer_id},
        )
        events = [result.to_event()]
        if not result.success:
            return {"events": events}
        events.append({
            "event": "business_context_loaded",
            "customer_id": customer_id,
            "customer": customer,
        })
        return {"business_context": result.data or {}, "events": events}

    async def _generate_suggestions(self, state: AgentGraphState) -> AgentGraphState:
        semantic_result = state.get("semantic_result")
        business_context = state.get("business_context") or {}
        if not semantic_result or not business_context or self._requires_clarification(semantic_result):
            return {}

        try:
            envelope = await self.suggestion_generator.generate_with_metadata(
                state["db"],
                team_id=state["team_id"],
                user_message=state.get("content", ""),
                semantic_result=semantic_result,
                customer_context=business_context,
            )
        except AgentSuggestionGeneratorError as exc:
            return {
                "suggestion_error": str(exc),
                "events": [{"event": "suggestion_failed", "message": str(exc)}],
            }

        return {
            "suggestion_result": envelope.result,
            "suggestion_metadata": {
                "suggestion_source": envelope.suggestion_source,
                "model": envelope.model,
            },
        }

    def _build_response(self, state: AgentGraphState) -> AgentGraphState:
        intent = state.get("intent") or "UNKNOWN"
        semantic_result = state.get("semantic_result")
        parsed = state.get("parsed") or {}
        candidates = state.get("customer_candidates") or []
        events = [{"event": "intent", "intent": intent}]

        if semantic_result:
            semantic_metadata = state.get("semantic_metadata") or {}
            events.append({
                "event": "semantic_parsed",
                "intent": semantic_result.intent,
                "confidence": semantic_result.intent_confidence,
                "parse_source": semantic_metadata.get("parse_source"),
                "model": semantic_metadata.get("model"),
                "need_clarification": semantic_result.need_clarification,
                "parsed": parsed,
            })

        suggestion_result = state.get("suggestion_result")
        if state.get("business_context"):
            events.append({
                "event": "business_context_loaded",
                "customer_id": (state.get("selected_customer") or {}).get("id"),
                "customer": state.get("selected_customer"),
            })
        if suggestion_result:
            suggestion_metadata = state.get("suggestion_metadata") or {}
            events.append({
                "event": "business_suggestions",
                "summary": suggestion_result.summary,
                "suggestions": [
                    suggestion.model_dump(exclude_none=True)
                    for suggestion in suggestion_result.suggestions
                ],
                "need_user_choice": suggestion_result.need_user_choice,
                "clarification_question": suggestion_result.clarification_question,
                "suggestion_source": suggestion_metadata.get("suggestion_source"),
                "model": suggestion_metadata.get("model"),
            })
        elif state.get("suggestion_error"):
            events.append({
                "event": "suggestion_failed",
                "message": state["suggestion_error"],
            })

        if state.get("events"):
            events.extend(state["events"])

        if state.get("semantic_error"):
            response = state["semantic_error"]
            events.append({"event": "final", "intent": intent, "content": response, "tool_execution_enabled": False})
            return {"response": response, "events": events}

        if self._requires_clarification(semantic_result):
            response = semantic_result.clarification_question or "我还不能可靠理解你的诉求，请补充客户名称、业务内容或要执行的动作。"
            events.append({
                "event": "clarification_required",
                "intent": intent,
                "content": response,
                "semantic": semantic_result.model_dump(exclude_none=True) if semantic_result else None,
            })
            events.append({"event": "final", "intent": intent, "content": response, "tool_execution_enabled": False})
            return {"response": response, "events": events}

        response, action = self._build_business_response(intent, parsed, candidates)
        if suggestion_result:
            response = self._append_suggestions_to_response(response, suggestion_result.suggestions)
        if action:
            event_name = "confirmation_required"
            if action.get("action") in {
                "select_customer_for_follow_up",
                "select_customer_for_contact",
                "select_customer_for_invoice_title",
                "select_customer_for_deployment_info",
            }:
                event_name = "customer_selection_required"
            elif action.get("action") == "collect_contact_fields":
                event_name = "contact_fields_required"
            elif action.get("action") == "collect_invoice_title_fields":
                event_name = "invoice_title_fields_required"
            elif action.get("action") == "collect_deployment_info_fields":
                event_name = "deployment_info_fields_required"
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
    def _requires_clarification(semantic_result: Optional[AgentSemanticParseResult]) -> bool:
        if semantic_result is None:
            return False
        return (
            semantic_result.need_clarification
            or semantic_result.intent == "UNKNOWN"
            or semantic_result.intent_confidence < 0.75
            or (
                semantic_result.intent != "UNKNOWN"
                and semantic_result.intent != "CUSTOMER_QUERY"
                and semantic_result.customer.confidence < 0.7
            )
        )

    def _parsed_from_semantic(self, semantic_result: AgentSemanticParseResult, original_content: str) -> Dict[str, Any]:
        contact = dict(semantic_result.contact or {})
        invoice_title = dict(semantic_result.invoice_title or {})
        deployment_info = dict(semantic_result.deployment_info or {})
        next_follow_time_iso = self.temporal_resolver.resolve_follow_up_time(
            semantic_result.follow_up.next_follow_time,
        )
        return {
            "customer_name": semantic_result.customer.name_text,
            "follow_up_content": semantic_result.follow_up.content or original_content,
            "method": semantic_result.follow_up.method or "AI录入",
            "contact": CRMAgentGraphService._drop_empty_values(contact),
            "missing_contact_fields": (
                semantic_result.missing_fields
                if semantic_result.intent == "CREATE_CONTACT" and semantic_result.missing_fields
                else CRMAgentGraphService.missing_contact_fields(contact)
                if semantic_result.intent == "CREATE_CONTACT"
                else []
            ),
            "invoice_title": CRMAgentGraphService._drop_empty_values(invoice_title),
            "missing_invoice_title_fields": (
                semantic_result.missing_fields
                if semantic_result.intent == "CREATE_INVOICE_TITLE" and semantic_result.missing_fields
                else CRMAgentGraphService.missing_invoice_title_fields(invoice_title)
                if semantic_result.intent == "CREATE_INVOICE_TITLE"
                else []
            ),
            "deployment_info": CRMAgentGraphService._drop_empty_values(deployment_info),
            "missing_deployment_info_fields": (
                semantic_result.missing_fields
                if semantic_result.intent == "CREATE_DEPLOYMENT_INFO" and semantic_result.missing_fields
                else CRMAgentGraphService.missing_deployment_info_fields(deployment_info)
                if semantic_result.intent == "CREATE_DEPLOYMENT_INFO"
                else []
            ),
            "next_action": semantic_result.follow_up.next_action,
            "next_follow_time_text": semantic_result.follow_up.next_follow_time_text,
            "next_follow_time_iso": next_follow_time_iso,
        }

    @staticmethod
    def _drop_empty_values(payload: Dict[str, Any]) -> Dict[str, Any]:
        return {key: value for key, value in payload.items() if value not in (None, "")}

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
                        "method": parsed.get("method") or "AI录入",
                        "next_action": parsed.get("next_action"),
                        "next_follow_time_text": parsed.get("next_follow_time_text"),
                        "next_follow_time_iso": parsed.get("next_follow_time_iso"),
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
                        "method": parsed.get("method") or "AI录入",
                        "next_action": parsed.get("next_action"),
                        "next_follow_time_text": parsed.get("next_follow_time_text"),
                        "next_follow_time_iso": parsed.get("next_follow_time_iso"),
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
            set_default = bool(invoice_title.pop("set_default", False))
            if len(candidates) == 1:
                customer = candidates[0]
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

        if intent == "CREATE_DEPLOYMENT_INFO":
            if not customer_name:
                return "我识别到这是创建部署信息，但还缺少明确客户名称。请补充客户名称。", None
            deployment_info = parsed.get("deployment_info") or {}
            missing_fields = CRMAgentGraphService.missing_deployment_info_fields(deployment_info)
            if len(candidates) == 1:
                customer = candidates[0]
                deployment_info["customer_id"] = customer.get("id")
                if missing_fields:
                    return (
                        f"我识别到要为「{customer.get('account_name')}」创建部署信息，"
                        f"还需要补充：{CRMAgentGraphService.format_deployment_info_missing_fields(missing_fields)}。"
                    ), {
                        "action": "collect_deployment_info_fields",
                        "customer": customer,
                        "payload": {
                            "customer_id": customer.get("id"),
                            "deployment_info": deployment_info,
                            "missing_fields": missing_fields,
                        },
                    }
                return (
                    f"我识别到要为「{customer.get('account_name')}」创建部署信息「{deployment_info.get('deployment_name')}」。"
                    "请确认是否创建？"
                ), {
                    "action": "create_deployment_info",
                    "customer": customer,
                    "payload": {
                        "customer_id": customer.get("id"),
                        "deployment_info": deployment_info,
                    },
                }
            if len(candidates) > 1:
                candidate_lines = [
                    f"{index}. {customer.get('account_name')}"
                    for index, customer in enumerate(candidates, start=1)
                ]
                return (
                    "我找到了多个可能的客户，请回复序号或客户名称确认要把部署信息创建到哪一个客户："
                    + "；".join(candidate_lines)
                ), {
                    "action": "select_customer_for_deployment_info",
                    "customers": candidates,
                    "payload": {
                        "deployment_info": deployment_info,
                        "missing_fields": missing_fields,
                    },
                }
            return f"我识别到要为「{customer_name}」创建部署信息，但当前没有搜索到可访问的客户。请确认客户名称是否正确。", None

        if intent == "CUSTOMER_QUERY":
            return "我识别到这是查询请求。下一步会接入客户上下文查询和汇总能力。", None

        return "我还不能可靠理解这条消息，请补充客户名称、业务内容或你希望我执行的动作。", None

    @staticmethod
    def _append_suggestions_to_response(response: str, suggestions: List[Any]) -> str:
        actionable = [
            suggestion
            for suggestion in suggestions
            if getattr(suggestion, "action", None) != "NO_ACTION" and getattr(suggestion, "confidence", 0.0) >= 0.7
        ]
        if not actionable:
            return response
        suggestion_lines = [
            f"{index}. {suggestion.title}"
            for index, suggestion in enumerate(actionable[:3], start=1)
        ]
        return response + "\n\n基于客户上下文，我建议下一步可以：" + "；".join(suggestion_lines) + "。"

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

    @staticmethod
    def missing_deployment_info_fields(deployment_info: Dict[str, Any]) -> List[str]:
        required_fields = ["deployment_name", "server_address", "authorized_users"]
        return [field for field in required_fields if not deployment_info.get(field)]

    @staticmethod
    def format_deployment_info_missing_fields(fields: List[str]) -> str:
        labels = {
            "deployment_name": "部署名称",
            "server_address": "服务器地址（需以 http:// 或 https:// 开头）",
            "authorized_users": "授权人数",
        }
        return "、".join(labels.get(field, field) for field in fields)


crm_agent_graph_service = CRMAgentGraphService()
