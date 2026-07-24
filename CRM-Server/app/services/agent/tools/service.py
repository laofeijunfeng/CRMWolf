"""Audited CRM AI Agent tools backed by existing CRM APIs."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from app.crud.agent import agent_idempotency_key_crud, agent_tool_call_crud
from app.models.agent import AgentIdempotencyStatus, AgentToolCallStatus
from app.schemas.agent import AgentIdempotencyKeyCreate, AgentIdempotencyKeyUpdate, AgentToolCallCreate, AgentToolCallUpdate
from app.services.agent.tools.api_client import CRMAPIClientError, InternalCRMAPIClient
from app.services.agent.tools.base import AgentToolContext, AgentToolResult, JsonDict


class CRMAgentToolService:
    """Agent tool facade.

    This class may persist Agent audit/idempotency state, but business data
    reads and writes must go through the existing API client.
    """

    def __init__(self, api_client: Optional[InternalCRMAPIClient] = None) -> None:
        self.api_client = api_client or InternalCRMAPIClient()

    async def search_customers(self, context: AgentToolContext, keyword: str, limit: int = 10) -> AgentToolResult:
        payload = {"keyword": keyword, "limit": limit, "scope": "accessible"}

        async def call_api():
            return await self.api_client.request(
                "GET",
                "/v1/customers/",
                context.authorization,
                params={"keyword": keyword, "limit": limit, "scope": "accessible"},
            )

        return await self._run_read_tool(context, "search_customers", payload, call_api)

    async def get_customer_context(self, context: AgentToolContext, customer_id: int) -> AgentToolResult:
        payload = {"customer_id": customer_id}

        async def call_api():
            detail = await self.api_client.request(
                "GET",
                f"/v1/customers/{customer_id}",
                context.authorization,
            )
            related = await self._get_customer_related_context(context, customer_id)
            return {"customer": detail, **related}

        return await self._run_read_tool(context, "get_customer_context", payload, call_api)

    async def create_customer_follow_up(
        self,
        context: AgentToolContext,
        customer_id: int,
        content: str,
        customer_name: Optional[str] = None,
        method: str = "AI录入",
        next_action: Optional[str] = None,
        next_follow_time: Optional[str] = None,
        idempotency_suffix: Optional[str] = None,
    ) -> AgentToolResult:
        payload = {
            "customer_id": customer_id,
            "customer_name": customer_name,
            "content": content,
            "method": method,
            "next_action": next_action,
            "next_follow_time": next_follow_time,
        }
        action_key = self._action_key("create_customer_follow_up", context, payload, idempotency_suffix)

        async def call_api():
            return await self.api_client.request(
                "POST",
                f"/v1/customer-follow-ups/{customer_id}",
                context.authorization,
                json={
                    "content": content,
                    "method": method,
                    "next_action": next_action,
                    "next_follow_time": next_follow_time,
                },
            )

        return await self._run_write_tool(context, "create_customer_follow_up", payload, action_key, call_api)

    async def create_contact(self, context: AgentToolContext, customer_id: int, contact: JsonDict) -> AgentToolResult:
        payload = {"customer_id": customer_id, "contact": contact}
        action_key = self._action_key("create_contact", context, payload, None)

        async def call_api():
            return await self.api_client.request(
                "POST",
                f"/v1/customers/{customer_id}/contacts",
                context.authorization,
                json=contact,
            )

        return await self._run_write_tool(context, "create_contact", payload, action_key, call_api)

    async def create_invoice_title(
        self,
        context: AgentToolContext,
        customer_id: int,
        invoice_title: JsonDict,
        set_default: bool = False,
    ) -> AgentToolResult:
        payload = {
            "customer_id": customer_id,
            "invoice_title": invoice_title,
            "set_default": set_default,
        }
        action_key = self._action_key("create_invoice_title", context, payload, None)

        async def call_api():
            created = await self.api_client.request(
                "POST",
                "/v1/invoice-titles",
                context.authorization,
                params={"customer_id": customer_id},
                json=invoice_title,
            )
            if set_default and isinstance(created, dict) and created.get("id"):
                updated = await self.api_client.request(
                    "PATCH",
                    f"/v1/invoice-titles/{created['id']}/set-default",
                    context.authorization,
                )
                return {"invoice_title": updated, "set_default": True}
            return {"invoice_title": created, "set_default": False}

        return await self._run_write_tool(context, "create_invoice_title", payload, action_key, call_api)

    async def create_deployment_info(
        self,
        context: AgentToolContext,
        deployment_info: JsonDict,
    ) -> AgentToolResult:
        payload = {"deployment_info": deployment_info}
        action_key = self._action_key("create_deployment_info", context, payload, None)

        async def call_api():
            return await self.api_client.request(
                "POST",
                "/v1/deployment-infos/",
                context.authorization,
                json=deployment_info,
            )

        return await self._run_write_tool(context, "create_deployment_info", payload, action_key, call_api)

    async def create_opportunity(
        self,
        context: AgentToolContext,
        opportunity: JsonDict,
        idempotency_suffix: Optional[str] = None,
    ) -> AgentToolResult:
        opportunity = {key: value for key, value in opportunity.items() if key != "opportunity_name"}
        payload = {"opportunity": opportunity}
        action_key = self._action_key("create_opportunity", context, payload, idempotency_suffix)

        async def call_api():
            return await self.api_client.request(
                "POST",
                "/v1/opportunities/",
                context.authorization,
                json=opportunity,
            )

        return await self._run_write_tool(context, "create_opportunity", payload, action_key, call_api)

    async def list_customer_opportunities(
        self,
        context: AgentToolContext,
        customer_id: int,
        status: Optional[str] = None,
        limit: int = 20,
    ) -> AgentToolResult:
        params: JsonDict = {"customer_id": customer_id, "limit": limit}
        if status is not None:
            params["status"] = status
        payload = dict(params)

        async def call_api():
            return await self.api_client.request(
                "GET",
                "/v1/opportunities/",
                context.authorization,
                params=params,
            )

        return await self._run_read_tool(context, "list_customer_opportunities", payload, call_api)

    async def get_opportunity_detail(self, context: AgentToolContext, opportunity_id: int) -> AgentToolResult:
        payload = {"opportunity_id": opportunity_id}

        async def call_api():
            return await self.api_client.request(
                "GET",
                f"/v1/opportunities/{opportunity_id}",
                context.authorization,
            )

        return await self._run_read_tool(context, "get_opportunity_detail", payload, call_api)

    async def get_opportunity_procurement_stages(
        self,
        context: AgentToolContext,
        opportunity_id: int,
    ) -> AgentToolResult:
        payload = {"opportunity_id": opportunity_id}

        async def call_api():
            return await self.api_client.request(
                "GET",
                f"/v1/opportunities/{opportunity_id}/procurement-stages",
                context.authorization,
            )

        return await self._run_read_tool(context, "get_opportunity_procurement_stages", payload, call_api)

    async def move_opportunity_stage(
        self,
        context: AgentToolContext,
        opportunity_id: int,
        stage_template_id: int,
        idempotency_suffix: Optional[str] = None,
    ) -> AgentToolResult:
        payload = {"opportunity_id": opportunity_id, "stage_template_id": stage_template_id}
        action_key = self._action_key("move_opportunity_stage", context, payload, idempotency_suffix)

        async def call_api():
            return await self.api_client.request(
                "POST",
                f"/v1/opportunities/{opportunity_id}/move-stage",
                context.authorization,
                json={"stage_template_id": stage_template_id},
            )

        return await self._run_write_tool(context, "move_opportunity_stage", payload, action_key, call_api)

    async def create_payment_plan(
        self,
        context: AgentToolContext,
        contract_id: int,
        stage_name: str,
        planned_amount: float,
        due_date: str,
        notes: Optional[str] = None,
        idempotency_suffix: Optional[str] = None,
    ) -> AgentToolResult:
        plan = {
            "stage_name": stage_name,
            "planned_amount": planned_amount,
            "due_date": due_date,
            "notes": notes,
        }
        payload = {"contract_id": contract_id, "plans": [plan]}
        action_key = self._action_key("create_payment_plan", context, payload, idempotency_suffix)

        async def call_api():
            created = await self.api_client.request(
                "POST",
                f"/v1/payments/contracts/{contract_id}/payment-plans",
                context.authorization,
                json={"plans": [plan]},
            )
            return {"items": created if isinstance(created, list) else [created]}

        return await self._run_write_tool(context, "create_payment_plan", payload, action_key, call_api)

    async def create_payment_record(
        self,
        context: AgentToolContext,
        payment_plan_id: int,
        actual_amount: float,
        payment_date: str,
        commission_member_id: str,
        actual_payer_name: Optional[str] = None,
        proof_attachment: Optional[str] = None,
        notes: Optional[str] = None,
        idempotency_suffix: Optional[str] = None,
    ) -> AgentToolResult:
        record = {
            "actual_amount": actual_amount,
            "actual_payer_name": actual_payer_name,
            "payment_date": payment_date,
            "proof_attachment": proof_attachment,
            "commission_member_id": commission_member_id,
            "notes": notes,
        }
        payload = {"payment_plan_id": payment_plan_id, **record}
        action_key = self._action_key("create_payment_record", context, payload, idempotency_suffix)

        async def call_api():
            return await self.api_client.request(
                "POST",
                f"/v1/payments/payment-plans/{payment_plan_id}/records",
                context.authorization,
                json=record,
            )

        return await self._run_write_tool(context, "create_payment_record", payload, action_key, call_api)

    async def _get_customer_related_context(self, context: AgentToolContext, customer_id: int) -> JsonDict:
        related_paths = {
            "opportunities": f"/v1/opportunities/?customer_id={customer_id}",
            "contracts": f"/v1/customers/{customer_id}/contracts",
            "payment_plans": f"/v1/customers/{customer_id}/payment-plans",
            "invoices": f"/v1/customers/{customer_id}/invoices",
            "invoice_titles": f"/v1/customers/{customer_id}/invoice-titles",
            "deployment_infos": f"/v1/deployment-infos/?customer_id={customer_id}",
            "follow_ups": f"/v1/customer-follow-ups/{customer_id}",
        }
        result: JsonDict = {}
        for key, path in related_paths.items():
            try:
                result[key] = await self.api_client.request("GET", path, context.authorization)
            except CRMAPIClientError as exc:
                result[key] = {"error": exc.message, "status_code": exc.status_code}
        result["active_opportunity_stage_context"] = await self._get_active_opportunity_stage_context(
            context,
            result.get("opportunities"),
        )
        return result

    async def _get_active_opportunity_stage_context(self, context: AgentToolContext, opportunities_value: Any) -> list[JsonDict]:
        opportunities = self._extract_items(opportunities_value)
        active_opportunities = [
            opportunity
            for opportunity in opportunities
            if str(opportunity.get("status")) == "0"
        ][:3]
        stage_context: list[JsonDict] = []
        for opportunity in active_opportunities:
            opportunity_id = opportunity.get("id")
            if not opportunity_id:
                continue
            try:
                detail = await self.api_client.request(
                    "GET",
                    f"/v1/opportunities/{opportunity_id}",
                    context.authorization,
                )
                stages = await self.api_client.request(
                    "GET",
                    f"/v1/opportunities/{opportunity_id}/procurement-stages",
                    context.authorization,
                )
                stage_context.append({
                    "opportunity": detail,
                    "procurement_stages": stages if isinstance(stages, list) else [],
                })
            except CRMAPIClientError as exc:
                stage_context.append({
                    "opportunity_id": opportunity_id,
                    "error": exc.message,
                    "status_code": exc.status_code,
                })
        return stage_context

    @staticmethod
    def _extract_items(value: Any) -> list[JsonDict]:
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            items = value.get("items")
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]
        return []

    async def _run_read_tool(
        self,
        context: AgentToolContext,
        tool_name: str,
        request_json: JsonDict,
        call_api: Callable[[], Any],
    ) -> AgentToolResult:
        tool_call = self._create_tool_call(context, tool_name, request_json)
        try:
            agent_tool_call_crud.mark_started(context.db, tool_call)
            data = await call_api()
            agent_tool_call_crud.update(
                context.db,
                tool_call,
                AgentToolCallUpdate(
                    status=AgentToolCallStatus.SUCCESS,
                    response_json={"data": data},
                    finished_time=datetime.now(),
                ),
            )
            return AgentToolResult(tool_name=tool_name, success=True, data=data, tool_call_id=tool_call.id)
        except CRMAPIClientError as exc:
            return self._mark_tool_failed(context, tool_call, tool_name, exc.message, exc.status_code, exc.response_json)
        except Exception as exc:
            return self._mark_tool_failed(context, tool_call, tool_name, str(exc), None, None)

    async def _run_write_tool(
        self,
        context: AgentToolContext,
        tool_name: str,
        request_json: JsonDict,
        action_key: str,
        call_api: Callable[[], Any],
    ) -> AgentToolResult:
        request_hash = self._hash_json(request_json)
        idempotency = agent_idempotency_key_crud.get_or_create(
            context.db,
            AgentIdempotencyKeyCreate(
                team_id=context.team_id,
                user_id=context.user_id,
                session_id=context.session_id,
                task_id=context.task_id,
                action_key=action_key,
                request_hash=request_hash,
            ),
        )
        if idempotency.status == AgentIdempotencyStatus.SUCCESS:
            return AgentToolResult(
                tool_name=tool_name,
                success=True,
                data=idempotency.result_json,
                idempotent_replay=True,
            )

        result = await self._run_read_tool(context, tool_name, request_json, call_api)
        if result.success:
            agent_idempotency_key_crud.update(
                context.db,
                idempotency,
                AgentIdempotencyKeyUpdate(status=AgentIdempotencyStatus.SUCCESS, result_json=result.data),
            )
        else:
            agent_idempotency_key_crud.update(
                context.db,
                idempotency,
                AgentIdempotencyKeyUpdate(status=AgentIdempotencyStatus.FAILED, error_message=result.error_message),
            )
        return result

    def _create_tool_call(self, context: AgentToolContext, tool_name: str, request_json: JsonDict):
        return agent_tool_call_crud.create(
            context.db,
            AgentToolCallCreate(
                call_key=f"call_{uuid.uuid4().hex}",
                team_id=context.team_id,
                user_id=context.user_id,
                session_id=context.session_id,
                task_id=context.task_id,
                tool_name=tool_name,
                request_json=request_json,
            ),
        )

    @staticmethod
    def _mark_tool_failed(
        context: AgentToolContext,
        tool_call,
        tool_name: str,
        message: str,
        status_code: Optional[int],
        response_json: Any,
    ) -> AgentToolResult:
        agent_tool_call_crud.update(
            context.db,
            tool_call,
            AgentToolCallUpdate(
                status=AgentToolCallStatus.FAILED,
                response_json={"data": response_json} if response_json is not None else None,
                error_message=message,
                finished_time=datetime.now(),
            ),
        )
        return AgentToolResult(
            tool_name=tool_name,
            success=False,
            error_message=message,
            status_code=status_code,
            tool_call_id=tool_call.id,
        )

    @staticmethod
    def _action_key(tool_name: str, context: AgentToolContext, payload: JsonDict, suffix: Optional[str]) -> str:
        stable_suffix = suffix or CRMAgentToolService._hash_json(payload)[:24]
        return f"{tool_name}:{context.session_id}:{stable_suffix}"

    @staticmethod
    def _hash_json(payload: JsonDict) -> str:
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
