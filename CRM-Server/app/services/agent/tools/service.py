"""Audited CRM AI Agent tools backed by existing CRM APIs."""
from __future__ import annotations

import hashlib
import json
import uuid
from typing import Callable, List, Optional, Union

from sqlalchemy import or_

from app.crud.agent import agent_idempotency_key_crud, agent_tool_call_crud
from app.crud.permission import permission_crud
from app.models.agent import AgentIdempotencyStatus, AgentToolCallStatus
from app.models.customer import Contact, Customer, CustomerMember
from app.models.lead import Lead, LeadStatus
from app.models.opportunity import Opportunity
from app.schemas.agent import (
    AgentIdempotencyKeyCreate,
    AgentIdempotencyKeyUpdate,
    AgentToolCallCreate,
    AgentToolCallUpdate,
)
from app.services.agent.tools.api_client import CRMAPIClientError, InternalCRMAPIClient
from app.services.agent.tools.base import AgentToolContext, AgentToolResult, JsonDict
from app.services.customer_alias_service import CustomerAliasService, customer_alias_service
from app.services.customer_identity_resolution_service import (
    CustomerIdentityResolutionService,
    customer_identity_resolution_service,
)
from app.services.customer_intelligence_context_service import (
    CustomerIntelligenceContextService,
    customer_intelligence_context_service,
)
from app.services.customer_knowledge_candidate_service import (
    CustomerKnowledgeCandidateResult,
    CustomerKnowledgeCandidateService,
    CustomerVisibilityPredicate,
    customer_knowledge_candidate_service,
)
from app.services.follow_up_task_confirmation_channel_service import (
    FollowUpTaskConfirmationChannelService,
    follow_up_task_confirmation_channel_service,
)
from app.services.follow_up_task_query_intent import normalize_follow_up_task_retrieval_mode
from app.services.follow_up_task_query_service import (
    FollowUpTaskQueryService,
    follow_up_task_query_service,
)
from app.services.follow_up_task_reconciliation_evaluation_service import FollowUpTaskReconciliationDecision
from app.services.follow_up_task_transition_execution_service import (
    FollowUpTaskTransitionExecutionService,
    FollowUpTaskTransitionExecutionStatus,
    follow_up_task_transition_execution_service,
)
from app.services.follow_up_task_transition_plan_service import (
    FollowUpTaskTransitionAction,
    FollowUpTaskTransitionActionType,
    FollowUpTaskTransitionPlan,
)
from app.services.work_summary_narrative_service import WorkSummaryNarrativeService
from app.services.work_summary_narrative_service import (
    work_summary_narrative_service as default_work_summary_narrative_service,
)
from app.services.work_summary_service import WorkSummaryService
from app.services.work_summary_service import work_summary_service as default_work_summary_service
from app.utils.public_id import is_opportunity_public_id
from app.utils.time import business_now


class CRMAgentToolService:
    """Agent tool facade.

    This class persists Agent audit/idempotency state. Normal user-facing reads
    and writes go through existing APIs; Agent-only internal checks can read
    directly when the result must follow a different disclosure policy.
    """

    def __init__(
        self,
        api_client: Optional[InternalCRMAPIClient] = None,
        intelligence_context_service: Optional[CustomerIntelligenceContextService] = None,
        knowledge_candidate_service: Optional[CustomerKnowledgeCandidateService] = None,
        alias_service: Optional[CustomerAliasService] = None,
        identity_resolution_service: Optional[CustomerIdentityResolutionService] = None,
        follow_up_query_service: Optional[FollowUpTaskQueryService] = None,
        follow_up_confirmation_channel_service: Optional[FollowUpTaskConfirmationChannelService] = None,
        follow_up_transition_execution_service: Optional[FollowUpTaskTransitionExecutionService] = None,
        work_summary_service: Optional[WorkSummaryService] = None,
        work_summary_narrative_service: Optional[WorkSummaryNarrativeService] = None,
    ) -> None:
        self.api_client = api_client or InternalCRMAPIClient()
        self.intelligence_context_service = intelligence_context_service or customer_intelligence_context_service
        self.knowledge_candidate_service = knowledge_candidate_service or customer_knowledge_candidate_service
        self.alias_service = alias_service or customer_alias_service
        self.identity_resolution_service = identity_resolution_service or customer_identity_resolution_service
        self.follow_up_query_service = follow_up_query_service or follow_up_task_query_service
        self.follow_up_confirmation_channel_service = (
            follow_up_confirmation_channel_service or follow_up_task_confirmation_channel_service
        )
        self.follow_up_transition_execution_service = (
            follow_up_transition_execution_service or follow_up_task_transition_execution_service
        )
        self.work_summary_service = work_summary_service or default_work_summary_service
        self.work_summary_narrative_service = work_summary_narrative_service or default_work_summary_narrative_service

    async def search_customers(self, context: AgentToolContext, keyword: str, limit: int = 10) -> AgentToolResult:
        clean_keyword = keyword.strip()
        expanded_terms = self.alias_service.expand_query_terms(clean_keyword)
        payload = {
            "keyword": clean_keyword,
            "limit": limit,
            "scope": "accessible",
            "retrieval_mode": "hybrid",
            "query_terms": expanded_terms,
        }

        async def call_api():
            lexical = await self.api_client.request(
                "GET",
                "/v1/customers/",
                context.authorization,
                params={"keyword": clean_keyword, "limit": limit, "scope": "accessible"},
            )
            return self._merge_customer_search_with_semantic_evidence(
                context,
                keyword=clean_keyword,
                lexical_data=lexical,
                limit=limit,
            )

        return await self._run_read_tool(context, "search_customers", payload, call_api)

    def _merge_customer_search_with_semantic_evidence(
        self,
        context: AgentToolContext,
        *,
        keyword: str,
        lexical_data: object,
        limit: int,
    ) -> JsonDict:
        lexical_payload = lexical_data if isinstance(lexical_data, dict) else {}
        lexical_items = [
            item for item in lexical_payload.get("items", [])
            if isinstance(item, dict) and isinstance(item.get("id"), (str, int)) and str(item.get("id"))
        ]
        visibility_predicate = self._customer_visibility_predicate(context)
        retrieval: JsonDict = {
            "mode": "hybrid",
            "lexical_status": "completed",
            "alias_status": "completed" if keyword else "skipped",
            "semantic_status": "not_attempted",
            "semantic_source": "customer_evidence",
        }
        semantic_candidates: list[JsonDict] = []
        if keyword:
            knowledge_result = self._search_accessible_customers_by_evidence(context, keyword, limit=limit)
            semantic_candidates = knowledge_result.candidates
            retrieval.update(_semantic_retrieval_metadata(knowledge_result.retrieval_event))
        resolution = self.identity_resolution_service.resolve(
            context.db,
            team_id=context.team_id,
            query_text=keyword,
            lexical_items=lexical_items,
            semantic_items=semantic_candidates,
            limit=limit,
            visibility_predicate=visibility_predicate,
        )
        items = resolution.items
        semantic_related_customers = resolution.related_customers
        retrieval.update(resolution.metadata)
        if semantic_related_customers:
            retrieval["semantic_related_customer_count"] = len(semantic_related_customers)
            retrieval["semantic_candidate_role"] = "related_evidence"
        return {
            **lexical_payload,
            "items": items,
            "semantic_related_customers": semantic_related_customers,
            "total": len(items),
            "retrieval": retrieval,
        }

    def _search_accessible_customers_by_evidence(
        self,
        context: AgentToolContext,
        keyword: str,
        *,
        limit: int,
    ) -> CustomerKnowledgeCandidateResult:
        return self.knowledge_candidate_service.recall(
            context.db,
            team_id=context.team_id,
            query_text=keyword,
            limit=limit,
            source_types=[
                "customer",
                "customer_profile",
                "customer_brief",
                "follow_up",
                "business_flow",
                "opportunity",
                "contract",
                "payment",
                "contact",
            ],
            visibility_predicate=self._customer_visibility_predicate(context),
        )

    def _customer_visibility_predicate(self, context: AgentToolContext) -> CustomerVisibilityPredicate:
        user_id = str(context.user_id)
        permission_flags: tuple[bool, bool] | None = None

        def can_view_customer(customer: Customer) -> bool:
            nonlocal permission_flags
            if permission_flags is None:
                permission_codes = {
                    permission.code
                    for permission in permission_crud.get_user_permissions(context.db, context.user_id, context.team_id)
                }
                permission_flags = (
                    "customer:view:all" in permission_codes,
                    "customer:view:own" in permission_codes,
                )
            customer_view_all, customer_view_own = permission_flags
            return self._can_view_customer(
                context,
                customer,
                user_id,
                customer_view_all,
                customer_view_own,
            )

        return can_view_customer

    async def search_creation_duplicates(
        self,
        context: AgentToolContext,
        customer_keywords: List[str],
        lead_keywords: List[str],
        phone: Optional[str] = None,
        limit: int = 10,
    ) -> AgentToolResult:
        payload = {
            "customer_keywords": self._clean_keywords(customer_keywords),
            "lead_keywords": self._clean_keywords(lead_keywords),
            "phone": phone.strip() if isinstance(phone, str) and phone.strip() else None,
            "limit": limit,
        }

        async def call_db():
            return self._search_creation_duplicates_in_db(
                context,
                customer_keywords=payload["customer_keywords"],
                lead_keywords=payload["lead_keywords"],
                phone=payload["phone"],
                limit=limit,
            )

        return await self._run_read_tool(context, "search_creation_duplicates", payload, call_db)

    def _search_creation_duplicates_in_db(
        self,
        context: AgentToolContext,
        customer_keywords: List[str],
        lead_keywords: List[str],
        phone: Optional[str],
        limit: int,
    ) -> JsonDict:
        permission_codes = {
            permission.code
            for permission in permission_crud.get_user_permissions(context.db, context.user_id, context.team_id)
        }
        user_id = str(context.user_id)
        customer_view_all = "customer:view:all" in permission_codes
        customer_view_own = "customer:view:own" in permission_codes
        lead_view_all = "lead:view:all" in permission_codes
        lead_view_own = "lead:view:own" in permission_codes

        customers = self._query_duplicate_customers(context, customer_keywords, phone, limit)
        leads = self._query_duplicate_leads(context, lead_keywords, phone, limit)

        visible_customers = []
        hidden_customer_count = 0
        for customer in customers:
            if self._can_view_customer(context, customer, user_id, customer_view_all, customer_view_own):
                visible_customers.append({
                    "id": customer.public_id,
                    "account_name": customer.account_name,
                    "visible": True,
                })
            else:
                hidden_customer_count += 1

        visible_leads = []
        hidden_lead_count = 0
        for lead in leads:
            if lead_view_all or (lead_view_own and (lead.owner_id == user_id or lead.creator_id == user_id)):
                visible_leads.append({
                    "id": lead.public_id,
                    "lead_name": lead.lead_name,
                    "contact_name": lead.contact_name,
                    "contact_phone": lead.contact_phone,
                    "visible": True,
                })
            else:
                hidden_lead_count += 1

        return {
            "customers": visible_customers,
            "leads": visible_leads,
            "hidden_customer_count": hidden_customer_count,
            "hidden_lead_count": hidden_lead_count,
        }

    def _query_duplicate_customers(
        self,
        context: AgentToolContext,
        keywords: List[str],
        phone: Optional[str],
        limit: int,
    ) -> List[Customer]:
        conditions = []
        for keyword in keywords:
            conditions.append(Customer.account_name.like(f"%{keyword}%"))
            conditions.append(Customer.account_name_norm.like(f"%{keyword}%"))
        if phone:
            conditions.append(
                context.db.query(Contact.id).filter(
                    Contact.team_id == context.team_id,
                    Contact.customer_id == Customer.id,
                    Contact.mobile == phone,
                ).exists()
            )
        if not conditions:
            return []
        return (
            context.db.query(Customer)
            .filter(Customer.team_id == context.team_id, or_(*conditions))
            .order_by(Customer.id.desc())
            .limit(limit)
            .all()
        )

    def _query_duplicate_leads(
        self,
        context: AgentToolContext,
        keywords: List[str],
        phone: Optional[str],
        limit: int,
    ) -> List[Lead]:
        conditions = []
        for keyword in keywords:
            conditions.append(Lead.lead_name.like(f"%{keyword}%"))
            conditions.append(Lead.contact_name.like(f"%{keyword}%"))
            conditions.append(Lead.contact_phone.like(f"%{keyword}%"))
        if phone:
            conditions.append(Lead.contact_phone == phone)
        if not conditions:
            return []
        return (
            context.db.query(Lead)
            .filter(
                Lead.team_id == context.team_id,
                Lead.status.notin_([LeadStatus.CONVERTED, LeadStatus.INVALID]),
                or_(*conditions),
            )
            .order_by(Lead.id.desc())
            .limit(limit)
            .all()
        )

    @staticmethod
    def _can_view_customer(
        context: AgentToolContext,
        customer: Customer,
        user_id: str,
        customer_view_all: bool,
        customer_view_own: bool,
    ) -> bool:
        if customer_view_all or (customer_view_own and customer.owner_id == user_id):
            return True
        return context.db.query(CustomerMember.id).filter(
            CustomerMember.team_id == context.team_id,
            CustomerMember.customer_id == customer.id,
            CustomerMember.user_id == user_id,
            CustomerMember.is_active.is_(True),
        ).first() is not None

    @staticmethod
    def _clean_keywords(keywords: List[str]) -> List[str]:
        cleaned = []
        for keyword in keywords:
            if not isinstance(keyword, str):
                continue
            value = keyword.strip()
            if value and value not in cleaned:
                cleaned.append(value)
        return cleaned

    async def get_customer_context(
        self,
        context: AgentToolContext,
        customer_id: Union[str, int],
        query_text: Optional[str] = None,
    ) -> AgentToolResult:
        payload = {"customer_id": customer_id, "query_text": query_text}

        async def call_api():
            customer_public_id = self._resolve_customer_public_id(context, customer_id)
            detail = await self.api_client.request(
                "GET",
                f"/v1/customers/{customer_public_id}",
                context.authorization,
            )
            related = await self._get_customer_related_context(context, customer_public_id)
            return {
                "customer": detail,
                **related,
                "customer_intelligence": self._get_customer_intelligence_payload(
                    context,
                    customer_id=self._customer_internal_id(context, customer_public_id),
                    query_text=query_text,
                ),
            }

        return await self._run_read_tool(context, "get_customer_context", payload, call_api)

    async def list_follow_up_tasks(
        self,
        context: AgentToolContext,
        *,
        status: str = "open",
        due_window: Optional[str] = None,
        customer_id: Optional[Union[str, int]] = None,
        owner_scope: str = "mine",
        query_text: Optional[str] = None,
        retrieval_mode: Optional[str] = None,
        limit: int = 50,
    ) -> AgentToolResult:
        normalized_retrieval_mode = normalize_follow_up_task_retrieval_mode(retrieval_mode, query_text)
        payload = {
            "status": status,
            "due_window": due_window,
            "customer_id": customer_id,
            "owner_scope": owner_scope,
            "query_text": query_text,
            "retrieval_mode": normalized_retrieval_mode,
            "limit": limit,
        }

        async def call_db():
            customer_public_id = self._resolve_customer_public_id(context, customer_id) if customer_id is not None else None
            return self.follow_up_query_service.list_tasks(
                context.db,
                team_id=context.team_id,
                user_id=context.user_id,
                status=status,
                due_window=due_window,
                customer_public_id=customer_public_id,
                owner_scope=owner_scope,
                query_text=query_text,
                retrieval_mode=normalized_retrieval_mode,
                limit=limit,
            )

        return await self._run_read_tool(context, "list_follow_up_tasks", payload, call_db)

    async def get_follow_up_task_detail(
        self,
        context: AgentToolContext,
        *,
        task_id: str,
    ) -> AgentToolResult:
        payload = {"task_id": task_id}

        async def call_db():
            return self.follow_up_query_service.get_task_detail(
                context.db,
                team_id=context.team_id,
                user_id=context.user_id,
                task_public_id=task_id,
            )

        return await self._run_read_tool(context, "get_follow_up_task_detail", payload, call_db)

    async def list_completed_work(
        self,
        context: AgentToolContext,
        *,
        window: str = "this_week",
        customer_id: Optional[Union[str, int]] = None,
        include_tasks: bool = True,
        include_activities: bool = True,
        include_business_events: bool = True,
        start_at: Optional[str] = None,
        end_at: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: int = 50,
    ) -> AgentToolResult:
        payload = {
            "window": window,
            "customer_id": customer_id,
            "include_tasks": include_tasks,
            "include_activities": include_activities,
            "include_business_events": include_business_events,
            "start_at": start_at,
            "end_at": end_at,
            "cursor": cursor,
            "limit": limit,
        }

        async def call_db():
            customer_public_id = self._resolve_customer_public_id(context, customer_id) if customer_id is not None else None
            return self.work_summary_service.list_completed_work(
                context.db,
                team_id=context.team_id,
                user_id=context.user_id,
                window=window,
                customer_public_id=customer_public_id,
                include_tasks=include_tasks,
                include_activities=include_activities,
                include_business_events=include_business_events,
                start_at=start_at,
                end_at=end_at,
                cursor=cursor,
                limit=limit,
            )

        return await self._run_read_tool(context, "list_completed_work", payload, call_db)

    async def summarize_completed_work(
        self,
        context: AgentToolContext,
        *,
        window: str = "this_week",
        customer_id: Optional[Union[str, int]] = None,
        include_tasks: bool = True,
        include_activities: bool = True,
        include_business_events: bool = True,
        start_at: Optional[str] = None,
        end_at: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: int = 50,
        question: Optional[str] = None,
    ) -> AgentToolResult:
        payload = {
            "window": window,
            "customer_id": customer_id,
            "include_tasks": include_tasks,
            "include_activities": include_activities,
            "include_business_events": include_business_events,
            "start_at": start_at,
            "end_at": end_at,
            "cursor": cursor,
            "limit": limit,
            "question": question,
        }

        async def call_db():
            customer_public_id = self._resolve_customer_public_id(context, customer_id) if customer_id is not None else None
            facts = self.work_summary_service.list_completed_work(
                context.db,
                team_id=context.team_id,
                user_id=context.user_id,
                window=window,
                customer_public_id=customer_public_id,
                include_tasks=include_tasks,
                include_activities=include_activities,
                include_business_events=include_business_events,
                start_at=start_at,
                end_at=end_at,
                cursor=cursor,
                limit=limit,
            )
            narrative = await self.work_summary_narrative_service.summarize_with_metadata(
                context.db,
                team_id=context.team_id,
                question=question or "总结我的工作",
                work_facts=facts,
            )
            return {
                "facts": facts,
                "narrative": narrative.result.model_dump(),
                "summary_source": narrative.summary_source,
                "model": narrative.model,
                "fallback_reason": narrative.fallback_reason,
                "fallback_error": narrative.fallback_error,
            }

        return await self._run_read_tool(context, "summarize_completed_work", payload, call_db)

    async def list_follow_up_task_confirmation_cases(
        self,
        context: AgentToolContext,
        *,
        limit: int = 20,
    ) -> AgentToolResult:
        payload = {"limit": limit}

        async def call_db():
            return self.follow_up_confirmation_channel_service.list_pending_cases(
                context.db,
                team_id=context.team_id,
                user_id=context.user_id,
                limit=limit,
            )

        return await self._run_read_tool(context, "list_follow_up_task_confirmation_cases", payload, call_db)

    async def resolve_follow_up_task_confirmation_case(
        self,
        context: AgentToolContext,
        *,
        case_id: str,
        reply_text: str,
        idempotency_suffix: Optional[str] = None,
    ) -> AgentToolResult:
        payload = {"case_id": case_id, "reply_text": reply_text}
        action_key = self._action_key(
            "resolve_follow_up_task_confirmation_case",
            context,
            payload,
            idempotency_suffix,
        )

        async def call_db():
            return self.follow_up_confirmation_channel_service.resolve_reply(
                context.db,
                team_id=context.team_id,
                user_id=context.user_id,
                case_public_id=case_id,
                reply_text=reply_text,
            )

        return await self._run_write_tool(
            context,
            "resolve_follow_up_task_confirmation_case",
            payload,
            action_key,
            call_db,
        )

    async def transition_follow_up_task(
        self,
        context: AgentToolContext,
        *,
        task_id: str,
        action: str,
        proposed_due_at: Optional[str] = None,
        reason: Optional[str] = None,
        idempotency_suffix: Optional[str] = None,
    ) -> AgentToolResult:
        payload = {
            "task_id": task_id,
            "action": action,
            "proposed_due_at": proposed_due_at,
            "reason": reason,
        }
        action_key = self._action_key("transition_follow_up_task", context, payload, idempotency_suffix)

        async def call_db():
            return self._execute_follow_up_task_transition(
                context,
                task_id=task_id,
                action=action,
                proposed_due_at=proposed_due_at,
                reason=reason,
            )

        return await self._run_write_tool(context, "transition_follow_up_task", payload, action_key, call_db)

    def _execute_follow_up_task_transition(
        self,
        context: AgentToolContext,
        *,
        task_id: str,
        action: str,
        proposed_due_at: Optional[str],
        reason: Optional[str],
    ) -> JsonDict:
        action_type = _follow_up_transition_action_type(action)
        decision = FollowUpTaskReconciliationDecision(
            decision=action_type,
            confidence=1.0,
            task_public_id=task_id,
            candidate_public_ids=(task_id,),
            needs_confirmation=False,
            proposed_due_at=proposed_due_at,
            evidence_terms=tuple(filter(None, [reason, "agent_confirmed_task_transition"])),
        )
        plan = FollowUpTaskTransitionPlan(
            decision=decision,
            actions=(
                FollowUpTaskTransitionAction(
                    action=action_type,
                    task_public_id=task_id,
                    confidence=1.0,
                    executable=action_type
                    in {
                        FollowUpTaskTransitionActionType.COMPLETE,
                        FollowUpTaskTransitionActionType.CANCEL,
                        FollowUpTaskTransitionActionType.DELAY,
                    },
                    requires_confirmation=False,
                    proposed_due_at=proposed_due_at,
                    reason=reason or "AGENT_CONFIRMED_TASK_TRANSITION",
                    evidence_terms=tuple(filter(None, [reason])),
                ),
            ),
            plan_source="agent_confirmed_task_transition",
            state_mutation_requested=False,
        )
        results = self.follow_up_transition_execution_service.execute_plan(
            context.db,
            team_id=context.team_id,
            plan=plan,
            actor_id=str(context.user_id),
            expected_owner_id=str(context.user_id),
            enabled=True,
            commit=True,
        )
        return {
            "plan": plan.to_dict(),
            "results": [result.to_dict() for result in results],
            "executed": any(
                result.status == FollowUpTaskTransitionExecutionStatus.EXECUTED for result in results
            ),
        }

    @staticmethod
    def _customer_internal_id(context: AgentToolContext, customer_public_id: Union[str, int]) -> int:
        if isinstance(customer_public_id, int) or (isinstance(customer_public_id, str) and customer_public_id.isdecimal()):
            customer = (
                context.db.query(Customer)
                .filter(Customer.team_id == context.team_id, Customer.id == int(customer_public_id))
                .first()
            )
            if customer is None:
                raise ValueError("客户不存在")
            return int(customer.id)
        customer = (
            context.db.query(Customer)
            .filter(Customer.team_id == context.team_id, Customer.public_id == customer_public_id)
            .first()
        )
        if customer is None:
            raise ValueError("客户不存在")
        return int(customer.id)

    @staticmethod
    def _resolve_customer_public_id(context: AgentToolContext, customer_id: Union[str, int]) -> str:
        if isinstance(customer_id, int) or (isinstance(customer_id, str) and customer_id.isdecimal()):
            customer = (
                context.db.query(Customer)
                .filter(Customer.team_id == context.team_id, Customer.id == int(customer_id))
                .first()
            )
            if customer is None:
                raise CRMAPIClientError("客户不存在或无权限访问", status_code=404)
            return str(customer.public_id)
        return str(customer_id)

    @staticmethod
    def _resolve_lead_public_id(context: AgentToolContext, lead_id: Union[str, int]) -> str:
        if isinstance(lead_id, int) or (isinstance(lead_id, str) and lead_id.isdecimal()):
            lead = (
                context.db.query(Lead)
                .filter(Lead.team_id == context.team_id, Lead.id == int(lead_id))
                .first()
            )
            if lead is None:
                raise CRMAPIClientError("线索不存在或无权限访问", status_code=404)
            return str(lead.public_id)
        return str(lead_id)

    def _get_customer_intelligence_payload(
        self,
        context: AgentToolContext,
        *,
        customer_id: int,
        query_text: Optional[str],
    ) -> JsonDict:
        try:
            intelligence_context = self.intelligence_context_service.build_context(
                context.db,
                team_id=context.team_id,
                customer_id=customer_id,
                query_text=query_text,
            )
            return intelligence_context.to_agent_payload()
        except Exception as exc:
            return {
                "retrieval": {
                    "status": "failed",
                    "enabled": False,
                    "error_message": str(exc),
                },
                "usage_policy": {
                    "strong_facts_source": "mysql",
                    "semantic_evidence_source": "qdrant",
                    "rule": "客户智能上下文暂不可用时, 继续使用当前工具返回的 CRM 业务上下文。",
                },
            }

    async def create_customer_activity(
        self,
        context: AgentToolContext,
        customer_id: Union[str, int],
        activity_kind: str,
        source_content: str,
        customer_name: Optional[str] = None,
        title: Optional[str] = None,
        next_action: Optional[str] = None,
        next_follow_time: Optional[str] = None,
        idempotency_suffix: Optional[str] = None,
    ) -> AgentToolResult:
        payload = {
            "customer_id": customer_id,
            "customer_name": customer_name,
            "activity_kind": activity_kind,
            "source_content": source_content,
            "title": title,
            "next_action": next_action,
            "next_follow_time": next_follow_time,
        }
        action_key = self._action_key("create_customer_activity", context, payload, idempotency_suffix)

        async def call_api():
            customer_public_id = self._resolve_customer_public_id(context, customer_id)
            return await self.api_client.request(
                "POST",
                f"/v1/customer-activities/{customer_public_id}",
                context.authorization,
                idempotency_key=action_key,
                params={"post_commit_mode": "sync"},
                json={
                    "activity_kind": activity_kind,
                    "source_content": source_content,
                    "title": title,
                    "next_action": next_action,
                    "next_follow_time": next_follow_time,
                    "next_follow_time_source": "AGENT" if next_follow_time else None,
                },
            )

        return await self._run_write_tool(context, "create_customer_activity", payload, action_key, call_api)

    async def create_lead(
        self,
        context: AgentToolContext,
        lead: JsonDict,
        idempotency_suffix: Optional[str] = None,
    ) -> AgentToolResult:
        payload = {"lead": lead}
        action_key = self._action_key("create_lead", context, payload, idempotency_suffix)

        async def call_api():
            return await self.api_client.request(
                "POST",
                "/v1/leads/",
                context.authorization,
                idempotency_key=action_key,
                json=lead,
            )

        return await self._run_write_tool(context, "create_lead", payload, action_key, call_api)

    async def create_customer(
        self,
        context: AgentToolContext,
        customer: JsonDict,
        idempotency_suffix: Optional[str] = None,
    ) -> AgentToolResult:
        payload = {"customer": customer}
        action_key = self._action_key("create_customer", context, payload, idempotency_suffix)

        async def call_api():
            return await self.api_client.request(
                "POST",
                "/v1/customers/",
                context.authorization,
                idempotency_key=action_key,
                json=customer,
            )

        return await self._run_write_tool(context, "create_customer", payload, action_key, call_api)

    async def create_lead_follow_up(
        self,
        context: AgentToolContext,
        lead_id: Union[str, int],
        content: str,
        method: str = "其他",
        next_action: Optional[str] = None,
        next_follow_time: Optional[str] = None,
        idempotency_suffix: Optional[str] = None,
    ) -> AgentToolResult:
        payload = {
            "lead_id": lead_id,
            "content": content,
            "method": method,
            "next_action": next_action,
            "next_follow_time": next_follow_time,
        }
        action_key = self._action_key("create_lead_follow_up", context, payload, idempotency_suffix)

        async def call_api():
            lead_public_id = self._resolve_lead_public_id(context, lead_id)
            return await self.api_client.request(
                "POST",
                f"/v1/leads/{lead_public_id}/follow-ups",
                context.authorization,
                idempotency_key=action_key,
                json={
                    "content": content,
                    "method": method,
                    "next_action": next_action,
                    "next_follow_time": next_follow_time,
                },
            )

        return await self._run_write_tool(context, "create_lead_follow_up", payload, action_key, call_api)

    async def create_contact(
        self,
        context: AgentToolContext,
        customer_id: Union[str, int],
        contact: JsonDict,
        idempotency_suffix: Optional[str] = None,
    ) -> AgentToolResult:
        payload = {"customer_id": customer_id, "contact": contact}
        action_key = self._action_key("create_contact", context, payload, idempotency_suffix)

        async def call_api():
            customer_public_id = self._resolve_customer_public_id(context, customer_id)
            return await self.api_client.request(
                "POST",
                f"/v1/customers/{customer_public_id}/contacts",
                context.authorization,
                idempotency_key=action_key,
                json=contact,
            )

        return await self._run_write_tool(context, "create_contact", payload, action_key, call_api)

    async def create_invoice_title(
        self,
        context: AgentToolContext,
        customer_id: Union[str, int],
        invoice_title: JsonDict,
        set_default: bool = False,
        idempotency_suffix: Optional[str] = None,
    ) -> AgentToolResult:
        payload = {
            "customer_id": customer_id,
            "invoice_title": invoice_title,
            "set_default": set_default,
        }
        action_key = self._action_key("create_invoice_title", context, payload, idempotency_suffix)

        async def call_api():
            customer_public_id = self._resolve_customer_public_id(context, customer_id)
            created = await self.api_client.request(
                "POST",
                "/v1/invoice-titles",
                context.authorization,
                idempotency_key=action_key,
                params={"customer_id": customer_public_id},
                json=invoice_title,
            )
            if set_default and isinstance(created, dict) and created.get("id"):
                updated = await self.api_client.request(
                    "PATCH",
                    f"/v1/invoice-titles/{created['id']}/set-default",
                    context.authorization,
                    idempotency_key=f"{action_key}:set-default",
                )
                return {"invoice_title": updated, "set_default": True}
            return {"invoice_title": created, "set_default": False}

        return await self._run_write_tool(context, "create_invoice_title", payload, action_key, call_api)

    async def create_deployment_info(
        self,
        context: AgentToolContext,
        deployment_info: JsonDict,
        idempotency_suffix: Optional[str] = None,
    ) -> AgentToolResult:
        payload = {"deployment_info": deployment_info}
        action_key = self._action_key("create_deployment_info", context, payload, idempotency_suffix)

        async def call_api():
            api_payload = dict(deployment_info)
            if api_payload.get("customer_id") is not None:
                api_payload["customer_id"] = self._resolve_customer_public_id(context, api_payload["customer_id"])
            return await self.api_client.request(
                "POST",
                "/v1/deployment-infos/",
                context.authorization,
                idempotency_key=action_key,
                json=api_payload,
            )

        return await self._run_write_tool(context, "create_deployment_info", payload, action_key, call_api)

    async def create_customer_member(
        self,
        context: AgentToolContext,
        customer_id: Union[str, int],
        member: JsonDict,
        idempotency_suffix: Optional[str] = None,
    ) -> AgentToolResult:
        payload = {"customer_id": customer_id, "member": member}
        action_key = self._action_key("create_customer_member", context, payload, idempotency_suffix)

        async def call_api():
            customer_public_id = self._resolve_customer_public_id(context, customer_id)
            return await self.api_client.request(
                "POST",
                f"/v1/customers/{customer_public_id}/members",
                context.authorization,
                idempotency_key=action_key,
                json=member,
            )

        return await self._run_write_tool(context, "create_customer_member", payload, action_key, call_api)

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
            api_payload = dict(opportunity)
            if api_payload.get("customer_id") is not None:
                api_payload["customer_id"] = self._resolve_customer_public_id(context, api_payload["customer_id"])
            return await self.api_client.request(
                "POST",
                "/v1/opportunities/",
                context.authorization,
                idempotency_key=action_key,
                json=api_payload,
            )

        return await self._run_write_tool(context, "create_opportunity", payload, action_key, call_api)

    async def list_customer_opportunities(
        self,
        context: AgentToolContext,
        customer_id: Union[str, int],
        status: Optional[str] = None,
        limit: int = 20,
    ) -> AgentToolResult:
        params: JsonDict = {"customer_id": customer_id, "limit": limit}
        if status is not None:
            params["status"] = status
        payload = dict(params)

        async def call_api():
            api_params = dict(params)
            api_params["customer_id"] = self._resolve_customer_public_id(context, customer_id)
            return await self.api_client.request(
                "GET",
                "/v1/opportunities/",
                context.authorization,
                params=api_params,
            )

        return await self._run_read_tool(context, "list_customer_opportunities", payload, call_api)

    async def get_opportunity_detail(self, context: AgentToolContext, opportunity_id: Union[str, int]) -> AgentToolResult:
        payload = {"opportunity_id": opportunity_id}

        async def call_api():
            opportunity_public_id = self._resolve_opportunity_public_id(context, opportunity_id)
            return await self.api_client.request(
                "GET",
                f"/v1/opportunities/{opportunity_public_id}",
                context.authorization,
            )

        return await self._run_read_tool(context, "get_opportunity_detail", payload, call_api)

    async def get_opportunity_procurement_stages(
        self,
        context: AgentToolContext,
        opportunity_id: Union[str, int],
    ) -> AgentToolResult:
        payload = {"opportunity_id": opportunity_id}

        async def call_api():
            opportunity_public_id = self._resolve_opportunity_public_id(context, opportunity_id)
            return await self.api_client.request(
                "GET",
                f"/v1/opportunities/{opportunity_public_id}/procurement-stages",
                context.authorization,
            )

        return await self._run_read_tool(context, "get_opportunity_procurement_stages", payload, call_api)

    async def move_opportunity_stage(
        self,
        context: AgentToolContext,
        opportunity_id: Union[str, int],
        stage_template_id: int,
        idempotency_suffix: Optional[str] = None,
    ) -> AgentToolResult:
        payload = {"opportunity_id": opportunity_id, "stage_template_id": stage_template_id}
        action_key = self._action_key("move_opportunity_stage", context, payload, idempotency_suffix)

        async def call_api():
            opportunity_public_id = self._resolve_opportunity_public_id(context, opportunity_id)
            return await self.api_client.request(
                "POST",
                f"/v1/opportunities/{opportunity_public_id}/move-stage",
                context.authorization,
                idempotency_key=action_key,
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
                idempotency_key=action_key,
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
                idempotency_key=action_key,
                json=record,
            )

        return await self._run_write_tool(context, "create_payment_record", payload, action_key, call_api)

    async def _get_customer_related_context(self, context: AgentToolContext, customer_id: str) -> JsonDict:
        related_paths = {
            "opportunities": f"/v1/opportunities/?customer_id={customer_id}",
            "contracts": f"/v1/customers/{customer_id}/contracts",
            "payment_plans": f"/v1/customers/{customer_id}/payment-plans",
            "invoices": f"/v1/customers/{customer_id}/invoices",
            "invoice_titles": f"/v1/customers/{customer_id}/invoice-titles",
            "deployment_infos": f"/v1/deployment-infos/?customer_id={customer_id}",
            "customer_activities": f"/v1/customer-activities/{customer_id}",
            "member_candidates": f"/v1/customers/{customer_id}/member-candidates",
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

    async def _get_active_opportunity_stage_context(self, context: AgentToolContext, opportunities_value: object) -> list[JsonDict]:
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
                opportunity_public_id = self._resolve_opportunity_public_id(context, opportunity_id)
                detail = await self.api_client.request(
                    "GET",
                    f"/v1/opportunities/{opportunity_public_id}",
                    context.authorization,
                )
                stages = await self.api_client.request(
                    "GET",
                    f"/v1/opportunities/{opportunity_public_id}/procurement-stages",
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
    def _resolve_opportunity_public_id(context: AgentToolContext, opportunity_id: Union[str, int]) -> str:
        if is_opportunity_public_id(opportunity_id):
            return str(opportunity_id)

        numeric_id: Optional[int] = None
        if isinstance(opportunity_id, int):
            numeric_id = opportunity_id
        elif isinstance(opportunity_id, str) and opportunity_id.isdecimal():
            numeric_id = int(opportunity_id)

        if numeric_id is None or numeric_id <= 0:
            raise CRMAPIClientError("商机对外ID格式不正确", status_code=404)

        opportunity = (
            context.db.query(Opportunity)
            .filter(Opportunity.id == numeric_id, Opportunity.team_id == context.team_id)
            .first()
        )
        if opportunity is None:
            raise CRMAPIClientError("商机不存在或无权限访问", status_code=404)
        return opportunity.public_id

    @staticmethod
    def _extract_items(value: object) -> list[JsonDict]:
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
        call_api: Callable[[], object],
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
                    finished_time=business_now(),
                ),
            )
            return AgentToolResult(tool_name=tool_name, success=True, data=data, tool_call_id=tool_call.id)
        except CRMAPIClientError as exc:
            return self._mark_tool_failed(context, tool_call, tool_name, exc.message, exc.status_code, exc.response_json)
        except Exception as exc:
            return self._mark_tool_failed(context, tool_call, tool_name, _exception_message(exc), None, None)

    async def _run_write_tool(
        self,
        context: AgentToolContext,
        tool_name: str,
        request_json: JsonDict,
        action_key: str,
        call_api: Callable[[], object],
    ) -> AgentToolResult:
        request_hash = self._hash_json(request_json)
        idempotency, created = agent_idempotency_key_crud.ensure(
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
        if idempotency.request_hash != request_hash:
            return AgentToolResult(
                tool_name=tool_name,
                success=False,
                error_message="idempotency_request_mismatch",
                status_code=409,
            )
        if idempotency.status == AgentIdempotencyStatus.SUCCESS:
            return AgentToolResult(
                tool_name=tool_name,
                success=True,
                data=idempotency.result_json,
                idempotent_replay=True,
            )
        if not created:
            if idempotency.status == AgentIdempotencyStatus.PENDING:
                agent_idempotency_key_crud.update(
                    context.db,
                    idempotency,
                    AgentIdempotencyKeyUpdate(
                        status=AgentIdempotencyStatus.AMBIGUOUS,
                        error_message="legacy_pending_write_requires_reconciliation",
                    ),
                )
            return AgentToolResult(
                tool_name=tool_name,
                success=False,
                error_message="idempotency_execution_ambiguous",
                status_code=409,
            )

        agent_idempotency_key_crud.update(
            context.db,
            idempotency,
            AgentIdempotencyKeyUpdate(
                status=AgentIdempotencyStatus.DISPATCHED,
                error_message=None,
            ),
        )
        result = await self._run_read_tool(context, tool_name, request_json, call_api)
        if result.success:
            agent_idempotency_key_crud.update(
                context.db,
                idempotency,
                AgentIdempotencyKeyUpdate(
                    status=AgentIdempotencyStatus.SUCCESS,
                    result_json=result.data,
                    error_message=None,
                ),
            )
        else:
            failure_status = (
                AgentIdempotencyStatus.FAILED
                if result.status_code is not None and 400 <= result.status_code < 500
                else AgentIdempotencyStatus.AMBIGUOUS
            )
            agent_idempotency_key_crud.update(
                context.db,
                idempotency,
                AgentIdempotencyKeyUpdate(status=failure_status, error_message=result.error_message),
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
        response_json: object,
    ) -> AgentToolResult:
        agent_tool_call_crud.update(
            context.db,
            tool_call,
            AgentToolCallUpdate(
                status=AgentToolCallStatus.FAILED,
                response_json={"data": response_json} if response_json is not None else None,
                error_message=message,
                finished_time=business_now(),
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


def _exception_message(exc: Exception) -> str:
    message = str(exc).strip()
    if message:
        return message
    return exc.__class__.__name__


def _compact_text(value: str | None, *, limit: int) -> str | None:
    if not value:
        return None
    compacted = " ".join(value.split())
    if len(compacted) <= limit:
        return compacted
    return f"{compacted[:limit - 1]}..."


def _follow_up_transition_action_type(action: str) -> str:
    return {
        "complete": FollowUpTaskTransitionActionType.COMPLETE,
        "cancel": FollowUpTaskTransitionActionType.CANCEL,
        "delay": FollowUpTaskTransitionActionType.DELAY,
        "keep_open": FollowUpTaskTransitionActionType.KEEP_OPEN,
    }.get(str(action or "").strip(), FollowUpTaskTransitionActionType.NOOP)


def _semantic_retrieval_metadata(event: JsonDict) -> JsonDict:
    status = event.get("status")
    if status == "ok":
        semantic_status = "completed"
    elif status == "embedding_unavailable":
        semantic_status = "unavailable"
    elif isinstance(status, str) and status:
        semantic_status = status
    else:
        semantic_status = "unknown"

    candidate_count = event.get("candidate_count")
    metadata: JsonDict = {
        "semantic_status": semantic_status,
        "semantic_candidate_count": candidate_count if isinstance(candidate_count, int) else 0,
    }
    reason = event.get("reason")
    if isinstance(reason, str) and reason.strip():
        metadata["semantic_unavailable_reason"] = reason
    return metadata
