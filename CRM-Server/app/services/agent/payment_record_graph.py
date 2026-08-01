"""Payment-record action-planning subgraph for the CRM Agent."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from sqlalchemy.exc import SQLAlchemyError

from app.services.agent import business_rules
from app.services.agent.checkpointer import (
    agent_checkpoint_saver,
    is_checkpoint_storage_error,
    with_checkpoint_unavailable_fallback_event,
)
from app.services.agent.state import (
    PaymentRecordPlanningGraphInput,
    PaymentRecordPlanningGraphResult,
    PaymentRecordPlanningGraphState,
    PaymentRecordPlanningRuntimeContext,
)
from app.services.agent.types import JSONDict, JSONValue, coerce_json_dict


PAYMENT_RECORD_CHECKPOINT_NS = "crm_agent_payment_record"

PaymentCustomerRoute = Literal[
    "missing_customer_name",
    "single_customer",
    "multiple_customers",
    "customer_not_found",
]
PaymentBusinessRoute = Literal[
    "no_contracts_no_opportunities",
    "no_contracts_with_opportunities",
    "missing_payment_fields",
    "missing_commission_member",
    "single_open_payment_plan",
    "multiple_open_payment_plans",
    "single_contract_without_open_plan",
    "multiple_contracts_without_open_plan",
]


def build_payment_record_thread_id(*, team_id: int, user_id: int, session_id: int) -> str:
    return f"crm_agent_payment_record:{team_id}:{user_id}:{session_id}"


def build_payment_record_graph_config(
    *,
    team_id: int,
    user_id: int,
    session_id: int,
) -> RunnableConfig:
        return {
            "configurable": {
                "thread_id": build_payment_record_thread_id(
                    team_id=team_id,
                    user_id=user_id,
                    session_id=session_id,
                ),
            },
            "metadata": {
                "team_id": team_id,
            "user_id": user_id,
            "session_id": session_id,
            "runtime": "crm_agent_payment_record",
            "runtime_namespace": PAYMENT_RECORD_CHECKPOINT_NS,
        },
    }


class PaymentRecordPlanningGraphService:
    """Plans payment-record responses and HITL actions through explicit graph branches."""

    def __init__(self, *, checkpointer: object | None = None) -> None:
        self._checkpoint_enabled = checkpointer is not None
        self._graph = self._build_graph(checkpointer)
        self._fallback_graph = self._build_graph(None)

    def _build_graph(self, checkpointer: object | None):
        graph = StateGraph(
            PaymentRecordPlanningGraphState,
            context_schema=PaymentRecordPlanningRuntimeContext,
        )
        graph.add_node("derive_customer_route", self._derive_customer_route)
        graph.add_node("missing_customer_name_response", self._missing_customer_name_response)
        graph.add_node("multiple_customers_response", self._multiple_customers_response)
        graph.add_node("customer_not_found_response", self._customer_not_found_response)
        graph.add_node("derive_payment_context", self._derive_payment_context)
        graph.add_node("no_contracts_no_opportunities_response", self._no_contracts_no_opportunities_response)
        graph.add_node("no_contracts_with_opportunities_response", self._no_contracts_with_opportunities_response)
        graph.add_node("missing_payment_fields_response", self._missing_payment_fields_response)
        graph.add_node("missing_commission_member_response", self._missing_commission_member_response)
        graph.add_node("single_open_payment_plan_response", self._single_open_payment_plan_response)
        graph.add_node("multiple_open_payment_plans_response", self._multiple_open_payment_plans_response)
        graph.add_node("single_contract_without_open_plan_response", self._single_contract_without_open_plan_response)
        graph.add_node(
            "multiple_contracts_without_open_plan_response",
            self._multiple_contracts_without_open_plan_response,
        )
        graph.add_edge(START, "derive_customer_route")
        graph.add_conditional_edges(
            "derive_customer_route",
            self._route_after_customer,
            {
                "missing_customer_name": "missing_customer_name_response",
                "single_customer": "derive_payment_context",
                "multiple_customers": "multiple_customers_response",
                "customer_not_found": "customer_not_found_response",
            },
        )
        graph.add_conditional_edges(
            "derive_payment_context",
            self._route_after_payment_context,
            {
                "no_contracts_no_opportunities": "no_contracts_no_opportunities_response",
                "no_contracts_with_opportunities": "no_contracts_with_opportunities_response",
                "missing_payment_fields": "missing_payment_fields_response",
                "missing_commission_member": "missing_commission_member_response",
                "single_open_payment_plan": "single_open_payment_plan_response",
                "multiple_open_payment_plans": "multiple_open_payment_plans_response",
                "single_contract_without_open_plan": "single_contract_without_open_plan_response",
                "multiple_contracts_without_open_plan": "multiple_contracts_without_open_plan_response",
            },
        )
        for node_name in [
            "missing_customer_name_response",
            "multiple_customers_response",
            "customer_not_found_response",
            "no_contracts_no_opportunities_response",
            "no_contracts_with_opportunities_response",
            "missing_payment_fields_response",
            "missing_commission_member_response",
            "single_open_payment_plan_response",
            "multiple_open_payment_plans_response",
            "single_contract_without_open_plan_response",
            "multiple_contracts_without_open_plan_response",
        ]:
            graph.add_edge(node_name, END)
        if checkpointer is None:
            return graph.compile()
        return graph.compile(checkpointer=checkpointer)

    async def run(self, input_state: PaymentRecordPlanningGraphInput) -> PaymentRecordPlanningGraphResult:
        checkpoint_state = _checkpoint_state_from_input(input_state)
        context = PaymentRecordPlanningRuntimeContext(
            team_id=int(input_state.get("team_id") or 0),
            user_id=int(input_state.get("user_id") or 0),
            session_id=int(input_state.get("session_id") or 0),
        )
        config = build_payment_record_graph_config(
            team_id=context.team_id,
            user_id=context.user_id,
            session_id=context.session_id,
        )
        try:
            return await self._graph.ainvoke(checkpoint_state, config, context=context)
        except SQLAlchemyError as exc:
            if not self._checkpoint_enabled or not is_checkpoint_storage_error(exc):
                raise
            result = await self._fallback_graph.ainvoke(checkpoint_state, config, context=context)
            return with_checkpoint_unavailable_fallback_event(
                result,
                runtime="crm_agent_payment_record",
                graph=PAYMENT_RECORD_CHECKPOINT_NS,
            )

    def _derive_customer_route(
        self,
        state: PaymentRecordPlanningGraphState,
        runtime: Runtime[PaymentRecordPlanningRuntimeContext],
    ) -> PaymentRecordPlanningGraphState:
        candidates = state.get("customer_candidates") or []
        if not state.get("customer_name"):
            return {"customer_route": "missing_customer_name"}
        if len(candidates) == 1:
            return {"customer_route": "single_customer", "selected_customer": candidates[0]}
        if len(candidates) > 1:
            return {"customer_route": "multiple_customers"}
        return {"customer_route": "customer_not_found"}

    def _route_after_customer(self, state: PaymentRecordPlanningGraphState) -> PaymentCustomerRoute:
        route = state.get("customer_route")
        if route in {"missing_customer_name", "single_customer", "multiple_customers", "customer_not_found"}:
            return route
        return "customer_not_found"

    def _missing_customer_name_response(self, state: PaymentRecordPlanningGraphState) -> PaymentRecordPlanningGraphState:
        return {"response": "我识别到这是回款场景，但还缺少明确客户名称。请补充客户名称。", "action": {}}

    def _multiple_customers_response(self, state: PaymentRecordPlanningGraphState) -> PaymentRecordPlanningGraphState:
        candidates = state.get("customer_candidates") or []
        candidate_lines = [
            f"{index}. {customer.get('account_name')}"
            for index, customer in enumerate(candidates, start=1)
        ]
        return {
            "response": "我找到了多个可能的客户，请告诉我要为哪一个客户处理回款：" + "；".join(candidate_lines),
            "action": {
                "action": "select_customer_for_payment_record",
                "customers": candidates,
                "payload": {
                    "payment": state.get("payment") or {},
                    "missing_fields": _string_list((state.get("parsed") or {}).get("missing_payment_fields")),
                },
            },
        }

    def _customer_not_found_response(self, state: PaymentRecordPlanningGraphState) -> PaymentRecordPlanningGraphState:
        return {
            "response": business_rules.customer_not_found_response(state.get("customer_name") or ""),
            "action": {},
        }

    def _derive_payment_context(
        self,
        state: PaymentRecordPlanningGraphState,
        runtime: Runtime[PaymentRecordPlanningRuntimeContext],
    ) -> PaymentRecordPlanningGraphState:
        business_context = state.get("business_context") or {}
        payment = state.get("payment") or {}
        contracts = _json_dict_list(business_rules.context_items(business_context.get("contracts")))
        opportunities = _json_dict_list(business_rules.context_items(business_context.get("opportunities")))
        payment_plans = _json_dict_list([
            plan
            for plan in business_rules.context_items(business_context.get("payment_plans"))
            if business_rules.is_open_payment_plan(plan)
        ])
        customer = state.get("selected_customer") or {}
        missing_fields = business_rules.missing_payment_fields(
            payment.get("actual_amount"),
            payment.get("payment_date_iso"),
        )
        commission_member_id = business_rules.resolve_commission_member_id(customer)
        update: PaymentRecordPlanningGraphState = {
            "contracts": contracts,
            "opportunities": opportunities,
            "payment_plans": payment_plans,
            "missing_fields": missing_fields,
            "commission_member_id": commission_member_id,
        }
        if not contracts:
            update["payment_route"] = (
                "no_contracts_with_opportunities" if opportunities else "no_contracts_no_opportunities"
            )
        elif missing_fields:
            update["payment_route"] = "missing_payment_fields"
        elif not commission_member_id:
            update["payment_route"] = "missing_commission_member"
        elif len(payment_plans) == 1:
            update["payment_route"] = "single_open_payment_plan"
        elif len(payment_plans) > 1:
            update["payment_route"] = "multiple_open_payment_plans"
        elif len(contracts) == 1:
            update["payment_route"] = "single_contract_without_open_plan"
        else:
            update["payment_route"] = "multiple_contracts_without_open_plan"
        return update

    def _route_after_payment_context(self, state: PaymentRecordPlanningGraphState) -> PaymentBusinessRoute:
        route = state.get("payment_route")
        if route in {
            "no_contracts_no_opportunities",
            "no_contracts_with_opportunities",
            "missing_payment_fields",
            "missing_commission_member",
            "single_open_payment_plan",
            "multiple_open_payment_plans",
            "single_contract_without_open_plan",
            "multiple_contracts_without_open_plan",
        }:
            return route
        return "multiple_contracts_without_open_plan"

    def _no_contracts_no_opportunities_response(
        self,
        state: PaymentRecordPlanningGraphState,
    ) -> PaymentRecordPlanningGraphState:
        customer = state.get("selected_customer") or {}
        return {
            "response": (
                f"我识别到「{customer.get('account_name')}」的回款信息，但没有找到商机和可用于登记回款的合同。"
                "按 CRM 业务链路，需要先补齐商机，再处理合同、回款计划和回款登记。"
                "创建合同暂未接入 Agent，因为当前创建合同需要上传合同附件。"
            ),
            "action": {},
        }

    def _no_contracts_with_opportunities_response(
        self,
        state: PaymentRecordPlanningGraphState,
    ) -> PaymentRecordPlanningGraphState:
        customer = state.get("selected_customer") or {}
        return {
            "response": (
                f"我识别到「{customer.get('account_name')}」的回款信息，但没有找到可用于登记回款的合同。"
                "该客户已有商机，但合同环节还未补齐；创建合同暂未接入 Agent，因为当前创建合同需要上传合同附件。"
            ),
            "action": {},
        }

    def _missing_payment_fields_response(
        self,
        state: PaymentRecordPlanningGraphState,
    ) -> PaymentRecordPlanningGraphState:
        customer = state.get("selected_customer") or {}
        missing_fields = state.get("missing_fields") or []
        return {
            "response": (
                f"我识别到「{customer.get('account_name')}」的回款信息，"
                f"还需要补充：{business_rules.format_payment_missing_fields(missing_fields)}。"
            ),
            "action": {
                "action": "collect_payment_fields",
                "customer": customer,
                "payload": {
                    "customer_id": customer.get("id"),
                    "payment": state.get("payment") or {},
                    "contracts": state.get("contracts") or [],
                    "payment_plans": state.get("payment_plans") or [],
                    "missing_fields": missing_fields,
                    "commission_member_id": state.get("commission_member_id"),
                },
            },
        }

    def _missing_commission_member_response(
        self,
        state: PaymentRecordPlanningGraphState,
    ) -> PaymentRecordPlanningGraphState:
        customer = state.get("selected_customer") or {}
        return {
            "response": (
                f"我识别到「{customer.get('account_name')}」的回款信息，但没有找到可用于登记的提成协作成员或负责人。"
                "请先在客户中配置协作成员或负责人后再登记。"
            ),
            "action": {},
        }

    def _single_open_payment_plan_response(
        self,
        state: PaymentRecordPlanningGraphState,
    ) -> PaymentRecordPlanningGraphState:
        customer = state.get("selected_customer") or {}
        plan = (state.get("payment_plans") or [{}])[0]
        return {
            "response": (
                f"我识别到「{customer.get('account_name')}」已回款，匹配到回款计划「{plan.get('stage_name')}」。"
                "请确认是否登记这笔回款？"
            ),
            "action": {
                "action": "create_payment_record",
                "customer": customer,
                "payload": business_rules.payment_record_payload(
                    plan,
                    state.get("payment") or {},
                    state.get("commission_member_id") or "",
                ),
            },
        }

    def _multiple_open_payment_plans_response(
        self,
        state: PaymentRecordPlanningGraphState,
    ) -> PaymentRecordPlanningGraphState:
        customer = state.get("selected_customer") or {}
        plans = state.get("payment_plans") or []
        plan_lines = [
            f"{index}. {plan.get('contract_name') or '未命名合同'} / {plan.get('stage_name')} / 待回款 {plan.get('remaining_amount')}"
            for index, plan in enumerate(plans, start=1)
        ]
        return {
            "response": "我找到了多个未完成回款计划，请告诉我要登记到哪一个计划：" + "；".join(plan_lines),
            "action": {
                "action": "select_payment_plan_for_record",
                "customer": customer,
                "payment_plans": plans,
                "payload": {
                    "customer_id": customer.get("id"),
                    "payment": state.get("payment") or {},
                    "commission_member_id": state.get("commission_member_id"),
                },
            },
        }

    def _single_contract_without_open_plan_response(
        self,
        state: PaymentRecordPlanningGraphState,
    ) -> PaymentRecordPlanningGraphState:
        customer = state.get("selected_customer") or {}
        contract = (state.get("contracts") or [{}])[0]
        return {
            "response": (
                f"我识别到「{customer.get('account_name')}」已回款，找到了合同「{contract.get('contract_name')}」，但没有找到回款计划。"
                "请确认是否先按本次回款金额创建一条回款计划？"
            ),
            "action": {
                "action": "create_payment_plan",
                "customer": customer,
                "payload": business_rules.payment_plan_payload(
                    contract,
                    state.get("payment") or {},
                    state.get("commission_member_id"),
                ),
            },
        }

    def _multiple_contracts_without_open_plan_response(
        self,
        state: PaymentRecordPlanningGraphState,
    ) -> PaymentRecordPlanningGraphState:
        customer = state.get("selected_customer") or {}
        contracts = state.get("contracts") or []
        contract_lines = [
            f"{index}. {contract.get('contract_name')} / 金额 {contract.get('total_amount')} / 状态 {contract.get('status')}"
            for index, contract in enumerate(contracts, start=1)
        ]
        return {
            "response": "我找到了多个合同，但没有可直接登记的回款计划。请告诉我要基于哪一个合同创建回款计划：" + "；".join(contract_lines),
            "action": {
                "action": "select_contract_for_payment_plan",
                "customer": customer,
                "contracts": contracts,
                "payload": {
                    "customer_id": customer.get("id"),
                    "payment": state.get("payment") or {},
                    "commission_member_id": state.get("commission_member_id"),
                },
            },
        }


def _checkpoint_state_from_input(input_state: PaymentRecordPlanningGraphInput) -> PaymentRecordPlanningGraphState:
    parsed = coerce_json_dict(input_state.get("parsed"))
    return {
        "team_id": int(input_state.get("team_id") or 0),
        "user_id": int(input_state.get("user_id") or 0),
        "session_id": int(input_state.get("session_id") or 0),
        "parsed": parsed,
        "customer_candidates": _json_dict_list(input_state.get("customer_candidates")),
        "business_context": coerce_json_dict(input_state.get("business_context")),
        "customer_name": _optional_string(parsed.get("customer_name")),
        "selected_customer": {},
        "payment": coerce_json_dict(parsed.get("payment")),
        "contracts": [],
        "opportunities": [],
        "payment_plans": [],
        "missing_fields": [],
        "commission_member_id": None,
        "customer_route": None,
        "payment_route": None,
        "response": None,
        "action": {},
    }


def _json_dict_list(value: object) -> list[JSONDict]:
    if not isinstance(value, list):
        return []
    return [coerce_json_dict(item) for item in value if isinstance(item, Mapping)]


def _string_list(value: JSONValue) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _optional_string(value: JSONValue) -> str | None:
    return value if isinstance(value, str) else None


payment_record_planning_graph_service = PaymentRecordPlanningGraphService(checkpointer=agent_checkpoint_saver)
