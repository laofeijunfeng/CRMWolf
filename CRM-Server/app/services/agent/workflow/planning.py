"""Plan typed CRM write commands for the durable Workflow subgraph."""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Protocol

from pydantic import ValidationError

from app.models.customer import Customer
from app.models.customer_activity import CustomerActivity
from app.models.customer_opportunity_suggestion_job import CustomerOpportunitySuggestionJob
from app.services.acquisition_source_service import resolve_write_fields_for_ai
from app.services.agent import business_rules
from app.services.agent.quality import (
    AgentFollowUpQualityEnvelope,
    AgentFollowUpQualityEvaluatorError,
    agent_follow_up_quality_evaluator,
)
from app.services.agent.schemas import AgentSemanticParseResult
from app.services.agent.semantic import (
    AgentSemanticParserError,
    agent_semantic_parser,
)
from app.services.agent.semantic_plan import workflow_intent_from_semantic_plan
from app.services.agent.temporal import agent_temporal_resolver
from app.services.agent.workflow.contracts import (
    WorkflowActionPlan,
    WorkflowAuthorizationBinding,
    WorkflowAuthorizationScope,
    WorkflowCommand,
    WorkflowCommandBinding,
    WorkflowInteraction,
    WorkflowInteractionField,
    WorkflowInteractionOption,
    WorkflowOpportunitySuggestionStart,
    WorkflowResolvedCustomer,
    WorkflowResourceStart,
    WorkflowRuntimeContext,
    WorkflowSupplement,
    WorkflowTextStart,
    WorkflowTurnInput,
)
from app.services.agent.workflow.customer_binding import bind_workflow_customer
from app.services.agent.workflow.resources import (
    CRMCustomerMemberResolver,
    CRMFollowUpTaskConfirmationCaseResolver,
    CRMFollowUpTaskResolver,
    CRMOpportunityProcurementMethodResolver,
    CRMOpportunityStageResolver,
    CRMWorkflowCustomerResolver,
    CustomerMemberResolver,
    FollowUpTaskConfirmationCaseResolver,
    FollowUpTaskResolution,
    FollowUpTaskResolver,
    OpportunityProcurementMethodResolver,
    OpportunityStageResolution,
    OpportunityStageResolver,
    ProcurementMethodResolution,
    WorkflowCustomerCandidate,
    WorkflowCustomerResolver,
    WorkflowResourceResolutionError,
)
from app.services.customer_activity_contracts import (
    CustomerActivitySubmissionSource,
    CustomerActivitySuggestionJobStatus,
)
from app.services.customer_activity_kinds import infer_activity_kind


class WorkflowPlanningError(ValueError):
    """A user request cannot be converted into an authorized write command."""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class WorkflowPlanningNeedsInput(Exception):
    """Planning paused because a recoverable business field is missing."""

    def __init__(
        self,
        interaction: WorkflowInteraction,
        *,
        checkpoint_request: WorkflowTurnInput | None = None,
    ) -> None:
        super().__init__(interaction.prompt)
        self.interaction = interaction
        self.checkpoint_request = checkpoint_request


class WorkflowSemanticParser(Protocol):
    async def parse_with_metadata(
        self,
        db: object,
        *,
        team_id: int,
        user_message: str,
        memory: object = None,
        current_date: date | None = None,
    ) -> object: ...


class WorkflowResourceRanker(Protocol):
    async def rank_resource_candidates(
        self,
        db: object,
        *,
        team_id: int,
        user_message: str,
        resource_kind: str,
        action_name: str,
        target: dict[str, object],
        candidates: list[dict[str, object]],
        current_date: date | None = None,
    ) -> list[dict[str, object]]: ...


class WorkflowFollowUpQualityEvaluator(Protocol):
    async def evaluate_with_metadata(
        self,
        db: object,
        *,
        team_id: int,
        user_message: str,
        semantic_result: object,
        memory: object = None,
        current_date: date | None = None,
    ) -> AgentFollowUpQualityEnvelope: ...


class WorkflowTemporalResolver(Protocol):
    def now(self) -> datetime: ...

    def resolve_follow_up_time(
        self,
        expression: object,
        *,
        base_datetime: datetime | None = None,
    ) -> str | None: ...

    def resolve_date(
        self,
        expression: object,
        *,
        base_datetime: datetime | None = None,
    ) -> str | None: ...


class CRMWorkflowPlanner:
    """Create one guarded CRM write plan from a Root-owned Workflow request."""

    def __init__(
        self,
        *,
        semantic_parser: WorkflowSemanticParser | None = None,
        resource_ranker: WorkflowResourceRanker | None = None,
        temporal_resolver: WorkflowTemporalResolver | None = None,
        follow_up_quality_evaluator: WorkflowFollowUpQualityEvaluator | None = None,
        customer_resolver: WorkflowCustomerResolver | None = None,
        customer_member_resolver: CustomerMemberResolver | None = None,
        follow_up_task_resolver: FollowUpTaskResolver | None = None,
        follow_up_confirmation_case_resolver: FollowUpTaskConfirmationCaseResolver | None = None,
        opportunity_procurement_method_resolver: OpportunityProcurementMethodResolver | None = None,
        opportunity_stage_resolver: OpportunityStageResolver | None = None,
    ) -> None:
        self._semantic_parser = semantic_parser or agent_semantic_parser
        self._resource_ranker = resource_ranker or (
            self._semantic_parser
            if hasattr(self._semantic_parser, "rank_resource_candidates")
            else None
        )
        self._temporal_resolver = temporal_resolver or agent_temporal_resolver
        self._follow_up_quality_evaluator = follow_up_quality_evaluator or agent_follow_up_quality_evaluator
        self._customer_resolver = customer_resolver or CRMWorkflowCustomerResolver()
        self._customer_member_resolver = customer_member_resolver or CRMCustomerMemberResolver()
        self._follow_up_task_resolver = follow_up_task_resolver or CRMFollowUpTaskResolver()
        self._follow_up_confirmation_case_resolver = (
            follow_up_confirmation_case_resolver or CRMFollowUpTaskConfirmationCaseResolver()
        )
        self._opportunity_procurement_method_resolver = (
            opportunity_procurement_method_resolver or CRMOpportunityProcurementMethodResolver()
        )
        self._opportunity_stage_resolver = opportunity_stage_resolver or CRMOpportunityStageResolver()

    async def _select_semantic_resource(
        self,
        *,
        runtime: WorkflowRuntimeContext,
        user_message: str,
        resource_kind: str,
        action_name: str,
        target: dict[str, object],
        candidates: list[dict[str, object]],
        team_id: int,
        current_date: date,
    ) -> dict[str, object] | None:
        """Let the configured model resolve ambiguous business resources.

        Resource resolvers remain authoritative for ownership and freshness,
        but they should not decide a natural-language reference by substring
        matching alone.  The LLM receives only the already-authorized
        candidates and returns an opaque ordinal; low-confidence or malformed
        output deliberately falls back to the existing UI choice.
        """

        if runtime.db is None or len(candidates) < 2:
            return None
        if self._resource_ranker is None:
            return None
        try:
            rankings = await self._resource_ranker.rank_resource_candidates(
                runtime.db,
                team_id=team_id,
                user_message=user_message,
                resource_kind=resource_kind,
                action_name=action_name,
                target=target,
                candidates=candidates,
                current_date=current_date,
            )
        except Exception:
            # Candidate ranking is an experience improvement, never an
            # availability dependency.  The signed choice interaction remains
            # the safe fallback when the model/provider is unavailable.
            return None

        if not isinstance(rankings, list):
            return None

        valid: list[tuple[int, float]] = []
        candidate_ids = {int(candidate["id"]) for candidate in candidates}
        for ranking in rankings:
            if not isinstance(ranking, dict):
                continue
            resource_id = ranking.get("resource_id")
            confidence = ranking.get("confidence")
            if isinstance(resource_id, bool) or not isinstance(resource_id, int):
                continue
            if resource_id not in candidate_ids or not isinstance(confidence, (int, float)):
                continue
            confidence_value = float(confidence)
            if not math.isfinite(confidence_value) or not 0.0 <= confidence_value <= 1.0:
                continue
            valid.append((resource_id, confidence_value))
        valid.sort(key=lambda item: item[1], reverse=True)
        if not valid or valid[0][1] < 0.90:
            return None
        if len(valid) > 1 and valid[0][1] - valid[1][1] < 0.10:
            return None
        return next(candidate for candidate in candidates if int(candidate["id"]) == valid[0][0])

    async def plan(
        self,
        request: WorkflowTurnInput,
        *,
        workflow_id: str,
        runtime: WorkflowRuntimeContext,
    ) -> WorkflowActionPlan:
        if isinstance(request.start, WorkflowResourceStart):
            return await self._plan_follow_up_confirmation_case(
                request,
                workflow_id=workflow_id,
                runtime=runtime,
            )
        if isinstance(request.start, WorkflowOpportunitySuggestionStart):
            return await self._plan_opportunity_suggestion(
                request,
                workflow_id=workflow_id,
                runtime=runtime,
            )
        if not isinstance(request.start, WorkflowTextStart):
            raise WorkflowPlanningError(
                "WORKFLOW_START_INVALID",
                "工作流启动参数无效。",
            )
        semantic = self._semantic_for_request(request)
        text = self._planning_text(request.start.text, request.supplements)
        db = runtime.db
        if db is None:
            raise WorkflowPlanningError(
                "WORKFLOW_DATABASE_REQUIRED",
                "工作流暂时无法读取业务配置。",
                retryable=True,
            )
        team_id = request.principal.team_id
        current_datetime = self._current_datetime(runtime)
        if semantic is None:
            try:
                envelope = await self._semantic_parser.parse_with_metadata(
                    db,
                    team_id=team_id,
                    user_message=text,
                    memory=None,
                    current_date=current_datetime.date(),
                )
            except AgentSemanticParserError as exc:
                raise WorkflowPlanningError(
                    "WORKFLOW_SEMANTIC_PARSE_FAILED",
                    "暂时无法理解这个写入请求,请稍后重试。",
                    retryable=True,
                ) from exc
            semantic = getattr(envelope, "result", None)

        if semantic is None:
            raise WorkflowPlanningError(
                "WORKFLOW_SEMANTIC_PARSE_FAILED",
                "暂时无法理解这个写入请求,请稍后重试。",
                retryable=True,
            )
        root_semantic_plan = request.start.semantic_plan
        expected_intent = self._workflow_intent_from_root_plan(root_semantic_plan)
        # Root and Workflow share the same model-produced semantic plan. The
        # detailed parser still extracts fields needed for the command, but it
        # must not turn an already-authorized activity assertion into a
        # different business intent on a second pass.
        if (
            expected_intent is not None
            and root_semantic_plan is not None
            and root_semantic_plan.confidence >= 0.80
            and hasattr(semantic, "model_copy")
        ):
            semantic = semantic.model_copy(
                update={
                    "intent": expected_intent,
                    "intent_confidence": max(
                        float(getattr(semantic, "intent_confidence", 0.0) or 0.0),
                        root_semantic_plan.confidence,
                    ),
                }
            )
        # Persist the normalized semantic result, including the Root-authorized
        # intent, as the canonical snapshot used by future resume turns.
        request = self._cache_semantic_snapshot(request, semantic)
        intent = getattr(semantic, "intent", None)
        confidence = getattr(semantic, "intent_confidence", 0.0)
        if not isinstance(confidence, (int, float)) or confidence < 0.75:
            raise WorkflowPlanningError(
                "WORKFLOW_INTENT_UNCERTAIN",
                "我还不能可靠判断要执行的业务操作,请补充更明确的操作和对象。",
            )
        if intent == "CUSTOMER_ACTIVITY":
            return await self._plan_customer_activity(
                semantic,
                request=request,
                workflow_id=workflow_id,
                runtime=runtime,
                current_datetime=current_datetime,
                user_message=text,
            )
        if intent == "CREATE_LEAD":
            return self._plan_lead(
                semantic,
                db=db,
                team_id=team_id,
                workflow_id=workflow_id,
                current_datetime=current_datetime,
            )
        if intent == "CREATE_CUSTOMER":
            return self._plan_customer(
                semantic,
                db=db,
                team_id=team_id,
                workflow_id=workflow_id,
                current_datetime=current_datetime,
            )
        if intent == "CREATE_CONTACT":
            return await self._plan_contact(
                semantic,
                request=request,
                workflow_id=workflow_id,
                runtime=runtime,
            )
        if intent == "CREATE_INVOICE_TITLE":
            return await self._plan_invoice_title(
                semantic,
                request=request,
                workflow_id=workflow_id,
                runtime=runtime,
            )
        if intent == "CREATE_DEPLOYMENT_INFO":
            return await self._plan_deployment_info(
                semantic,
                request=request,
                workflow_id=workflow_id,
                runtime=runtime,
            )
        if intent == "CREATE_CUSTOMER_MEMBER":
            return await self._plan_customer_member(
                semantic,
                request=request,
                workflow_id=workflow_id,
                runtime=runtime,
            )
        if intent == "CREATE_OPPORTUNITY":
            return await self._plan_opportunity(
                semantic,
                request=request,
                workflow_id=workflow_id,
                runtime=runtime,
                current_datetime=current_datetime,
            )
        if intent == "MOVE_OPPORTUNITY_STAGE":
            return await self._plan_opportunity_stage_transition(
                semantic,
                request=request,
                workflow_id=workflow_id,
                runtime=runtime,
                current_datetime=current_datetime,
                user_message=text,
            )
        if intent == "FOLLOW_UP_TASK_TRANSITION":
            return await self._plan_follow_up_task_transition(
                semantic,
                request=request,
                workflow_id=workflow_id,
                runtime=runtime,
                current_datetime=current_datetime,
            )
        raise WorkflowPlanningError(
            "WORKFLOW_ACTION_UNSUPPORTED",
            "当前工作流尚不能可靠执行这个写入请求。",
        )

    @staticmethod
    def _workflow_intent_from_root_plan(plan: object) -> str | None:
        """Project Root's authorized write capability into a Workflow intent."""

        return workflow_intent_from_semantic_plan(plan)

    async def _plan_customer_activity(
        self,
        semantic: object,
        *,
        request: WorkflowTurnInput,
        workflow_id: str,
        runtime: WorkflowRuntimeContext,
        current_datetime: datetime,
        user_message: str,
    ) -> WorkflowActionPlan:
        customer_id, customer_name = await self._resolve_customer(
            semantic,
            request=request,
            workflow_id=workflow_id,
            runtime=runtime,
        )
        checkpoint_request = self._with_resolved_customer(
            request,
            semantic=semantic,
            customer_id=customer_id,
            customer_name=customer_name,
        )
        follow_up = getattr(semantic, "follow_up", None)
        content = getattr(follow_up, "content", None)
        if not isinstance(content, str) or not content.strip():
            raise self._needs_text(
                workflow_id=workflow_id,
                field="follow_up_content",
                business_action="provide_follow_up_content",
                title="补充跟进内容",
                prompt="请补充本次客户跟进的具体内容。",
                checkpoint_request=checkpoint_request,
            )
        content = content.strip()
        method = getattr(follow_up, "method", None)
        next_action = getattr(follow_up, "next_action", None)
        next_action = next_action.strip() if isinstance(next_action, str) and next_action.strip() else None
        next_follow_time = self._temporal_resolver.resolve_follow_up_time(
            getattr(follow_up, "next_follow_time", None),
            base_datetime=current_datetime,
        )
        try:
            quality_envelope = await self._follow_up_quality_evaluator.evaluate_with_metadata(
                runtime.db,
                team_id=request.principal.team_id,
                user_message=user_message,
                semantic_result=semantic,
                current_date=current_datetime.date(),
            )
        except AgentFollowUpQualityEvaluatorError as exc:
            raise WorkflowPlanningError(
                "WORKFLOW_FOLLOW_UP_QUALITY_EVALUATION_FAILED",
                "暂时无法完成跟进质量评估，请稍后重试。",  # noqa: RUF001
                retryable=True,
            ) from exc

        quality = quality_envelope.result
        if not quality.passed:
            raise WorkflowPlanningNeedsInput(
                WorkflowInteraction(
                    interaction_id=f"int_{workflow_id.removeprefix('wf_')}_follow_up_quality",
                    interaction_type="text_input",
                    business_action="supplement_follow_up_quality",
                    title="补充跟进信息",
                    prompt=(
                        quality.supplement_question
                        or "这条跟进还差一点关键信息，请补充下一步由谁在什么时间做什么。"  # noqa: RUF001
                    ),
                    allow_blank=False,
                    submit_label="继续评估",
                ),
                checkpoint_request=checkpoint_request,
            )
        next_action_status = getattr(quality, "next_action_status", "MISSING")
        # The evaluator is the semantic authority for this gate.  The only
        # deterministic safeguard here is structural: a model cannot mark a
        # record as CLEAR while the parsed activity contains no action at all.
        if next_action_status == "CLEAR" and not next_action:
            next_action_status = "MISSING"
        if next_action_status in {"MISSING", "VAGUE"}:
            raise WorkflowPlanningNeedsInput(
                WorkflowInteraction(
                    interaction_id=f"int_{workflow_id.removeprefix('wf_')}_follow_up_next_action",
                    interaction_type="text_input",
                    business_action="supplement_follow_up_next_action",
                    title="补充下一步行动",
                    prompt="这条跟进还没有明确的下一步行动，请补充下一步由谁在什么时间做什么。",  # noqa: RUF001
                    allow_blank=False,
                    submit_label="继续评估",
                ),
                checkpoint_request=checkpoint_request,
            )

        final_content = (quality.suggested_revision or content).strip()
        persisted_next_action = None if next_action_status == "EXPLICITLY_NONE" else next_action
        payload: dict[str, object] = {
            "customer_id": customer_id,
            "customer_name": customer_name,
            "activity_kind": infer_activity_kind(method, final_content),
            "source_content": content,
            "title": final_content,
            "content_json": {"content": final_content},
            "summary": final_content[:200],
            "next_action": persisted_next_action,
            "next_action_source": "AGENT",
            "next_follow_time": next_follow_time,
            "next_follow_time_source": "AGENT" if next_follow_time else None,
            "effectiveness_score": quality.score,
            "effectiveness_is_valid": quality.passed,
            "effectiveness_reason": quality.reason,
            "effectiveness_detail_json": {
                key: value.model_dump(mode="json")
                for key, value in quality.principle_scores.items()
            },
        }
        intent_confidence = float(getattr(semantic, "intent_confidence", 0.0) or 0.0)
        if intent_confidence >= 0.85:
            return self._auto_execute_plan(
                workflow_id=workflow_id,
                action_type="create_customer_activity",
                payload=payload,
                authorized_customer_ids=[customer_id],
                confidence=intent_confidence,
                completed_text=f"已记录{customer_name}的本次跟进。",
                cancelled_text=f"已取消记录{customer_name}的本次跟进。",
            )
        return self._confirmation_plan(
            workflow_id=workflow_id,
            action_type="create_customer_activity",
            payload=payload,
            authorized_customer_ids=[customer_id],
            title="确认记录客户跟进",
            prompt=f"确认要为「{customer_name}」记录本次跟进“{content}”吗?",
            confirm_label="确认创建",
            completed_text=f"已记录{customer_name}的本次跟进。",
            cancelled_text=f"已取消记录{customer_name}的本次跟进。",
        )

    def _plan_lead(
        self,
        semantic: object,
        *,
        db: object,
        team_id: int,
        workflow_id: str,
        current_datetime: datetime,
    ) -> WorkflowActionPlan:
        lead_model = getattr(semantic, "lead", None)
        lead = {
            key: value
            for key, value in {
                "lead_name": getattr(lead_model, "lead_name", None),
                "source": getattr(lead_model, "source", None),
                "city": getattr(lead_model, "city", None),
                "contact_name": getattr(lead_model, "contact_name", None),
                "contact_phone": getattr(lead_model, "contact_phone", None),
                "company_scale": getattr(lead_model, "company_scale", None),
            }.items()
            if value is not None and value != ""
        }
        lead = resolve_write_fields_for_ai(lead, db, team_id)
        missing_fields = business_rules.missing_lead_fields(lead)
        if missing_fields:
            raise self._needs_text(
                workflow_id=workflow_id,
                field="lead_fields",
                business_action="provide_lead_fields",
                title="补充线索信息",
                prompt=f"还需要补充:{business_rules.format_lead_missing_fields(missing_fields)}。",
            )
        lead_name = str(lead["lead_name"])
        follow_up_content = getattr(lead_model, "follow_up_content", None)
        if not isinstance(follow_up_content, str) or not follow_up_content.strip():
            return self._confirmation_plan(
                workflow_id=workflow_id,
                action_type="create_lead",
                payload={"lead": lead},
                authorized_customer_ids=[],
                title="确认创建线索",
                prompt=f"确认要创建线索“{lead_name}”吗?",
                confirm_label="确认创建",
                completed_text=f"已创建线索“{lead_name}”。",
                cancelled_text=f"已取消创建线索“{lead_name}”。",
            )

        follow_up_payload: dict[str, object] = {
            "content": follow_up_content.strip(),
            "method": getattr(lead_model, "follow_up_method", None) or "其他",
        }
        next_action = getattr(lead_model, "next_action", None)
        if isinstance(next_action, str) and next_action.strip():
            follow_up_payload["next_action"] = next_action.strip()
        next_follow_time = self._temporal_resolver.resolve_follow_up_time(
            getattr(lead_model, "next_follow_time", None),
            base_datetime=current_datetime,
        )
        if next_follow_time:
            follow_up_payload["next_follow_time"] = next_follow_time
        return self._confirmation_commands_plan(
            workflow_id=workflow_id,
            business_action="create_lead_with_follow_up",
            commands=[
                WorkflowCommand(
                    command_id="create_lead",
                    tool_name="create_lead",
                    payload={"lead": lead},
                    authorization_scope=WorkflowAuthorizationScope(customer_ids=[]),
                ),
                WorkflowCommand(
                    command_id="create_lead_follow_up",
                    tool_name="create_lead_follow_up",
                    payload=follow_up_payload,
                    authorization_scope=WorkflowAuthorizationScope(customer_ids=[]),
                    bindings=[
                        WorkflowCommandBinding(
                            target_path=["lead_id"],
                            source_command_id="create_lead",
                            source_path=["id"],
                        )
                    ],
                ),
            ],
            title="确认创建线索并记录跟进",
            prompt=f"确认要创建线索“{lead_name}”并记录首次跟进吗?",
            confirm_label="确认创建",
            completed_text=f"已创建线索“{lead_name}”并记录首次跟进。",
            cancelled_text=f"已取消创建线索“{lead_name}”及首次跟进。",
        )

    def _plan_customer(
        self,
        semantic: object,
        *,
        db: object,
        team_id: int,
        workflow_id: str,
        current_datetime: datetime,
    ) -> WorkflowActionPlan:
        customer_model = getattr(semantic, "customer_create", None)
        flat_customer = {
            key: value
            for key, value in {
                "account_name": getattr(customer_model, "account_name", None),
                "source": getattr(customer_model, "source", None),
                "city": getattr(customer_model, "city", None),
                "industry": getattr(customer_model, "industry", None),
                "company_scale": getattr(customer_model, "company_scale", None),
                "contact_name": getattr(customer_model, "contact_name", None),
                "contact_phone": getattr(customer_model, "contact_phone", None),
                "contact_position": getattr(customer_model, "contact_position", None),
                "contact_gender": getattr(customer_model, "contact_gender", None),
                "contact_email": getattr(customer_model, "contact_email", None),
            }.items()
            if value is not None and value != ""
        }
        flat_customer = resolve_write_fields_for_ai(flat_customer, db, team_id)
        missing_fields = business_rules.missing_customer_fields(flat_customer)
        if missing_fields:
            raise self._needs_text(
                workflow_id=workflow_id,
                field="customer_fields",
                business_action="provide_customer_fields",
                title="补充客户信息",
                prompt=f"还需要补充:{business_rules.format_customer_missing_fields(missing_fields)}。",
            )
        customer = self._customer_create_payload(flat_customer)
        account_name = str(customer["account_name"])
        follow_up_content = getattr(customer_model, "follow_up_content", None)
        if not isinstance(follow_up_content, str) or not follow_up_content.strip():
            return self._confirmation_plan(
                workflow_id=workflow_id,
                action_type="create_customer",
                payload={"customer": customer},
                authorized_customer_ids=[],
                title="确认创建客户",
                prompt=f"确认要创建客户“{account_name}”吗?",
                confirm_label="确认创建",
                completed_text=f"已创建客户“{account_name}”。",
                cancelled_text=f"已取消创建客户“{account_name}”。",
            )

        content = follow_up_content.strip()
        method = getattr(customer_model, "follow_up_method", None)
        activity_payload: dict[str, object] = {
            "customer_name": account_name,
            "activity_kind": infer_activity_kind(method, content),
            "source_content": content,
            "title": content,
        }
        next_action = getattr(customer_model, "next_action", None)
        if isinstance(next_action, str) and next_action.strip():
            activity_payload["next_action"] = next_action.strip()
        next_follow_time = self._temporal_resolver.resolve_follow_up_time(
            getattr(customer_model, "next_follow_time", None),
            base_datetime=current_datetime,
        )
        if next_follow_time:
            activity_payload["next_follow_time"] = next_follow_time
        return self._confirmation_commands_plan(
            workflow_id=workflow_id,
            business_action="create_customer_with_activity",
            commands=[
                WorkflowCommand(
                    command_id="create_customer",
                    tool_name="create_customer",
                    payload={"customer": customer},
                    authorization_scope=WorkflowAuthorizationScope(customer_ids=[]),
                ),
                WorkflowCommand(
                    command_id="create_customer_activity",
                    tool_name="create_customer_activity",
                    payload=activity_payload,
                    authorization_scope=WorkflowAuthorizationScope(
                        customer_ids=[],
                        customer_bindings=[
                            WorkflowAuthorizationBinding(
                                source_command_id="create_customer",
                                source_path=["id"],
                            )
                        ],
                    ),
                    bindings=[
                        WorkflowCommandBinding(
                            target_path=["customer_id"],
                            source_command_id="create_customer",
                            source_path=["id"],
                        )
                    ],
                ),
            ],
            title="确认创建客户并记录跟进",
            prompt=f"确认要创建客户“{account_name}”并记录首次跟进吗?",
            confirm_label="确认创建",
            completed_text=f"已创建客户“{account_name}”并记录首次跟进。",
            cancelled_text=f"已取消创建客户“{account_name}”及首次跟进。",
        )

    async def _plan_contact(
        self,
        semantic: object,
        *,
        request: WorkflowTurnInput,
        workflow_id: str,
        runtime: WorkflowRuntimeContext,
    ) -> WorkflowActionPlan:
        customer_id, customer_name = await self._resolve_customer(
            semantic,
            request=request,
            workflow_id=workflow_id,
            runtime=runtime,
        )
        raw_contact = getattr(semantic, "contact", None)
        contact_source = raw_contact if isinstance(raw_contact, dict) else {}
        contact = {
            key: value
            for key in (
                "name",
                "gender",
                "position",
                "is_decision_maker",
                "mobile",
                "email",
                "wechat_id",
                "remark",
                "reports_to",
            )
            if (value := contact_source.get(key)) is not None and value != ""
        }
        missing_fields = business_rules.missing_contact_fields(contact)
        if missing_fields:
            raise self._needs_text(
                workflow_id=workflow_id,
                field="contact_fields",
                business_action="provide_contact_fields",
                title="补充联系人信息",
                prompt=f"还需要补充:{business_rules.format_contact_missing_fields(missing_fields)}。",
            )
        contact_name = str(contact["name"])
        return self._confirmation_plan(
            workflow_id=workflow_id,
            action_type="create_contact",
            payload={
                "customer_id": customer_id,
                "contact": contact,
            },
            authorized_customer_ids=[customer_id],
            title="确认创建联系人",
            prompt=f"确认要为「{customer_name}」创建联系人“{contact_name}”吗?",
            confirm_label="确认创建",
            completed_text=f"已为{customer_name}创建联系人“{contact_name}”。",
            cancelled_text=f"已取消为{customer_name}创建联系人“{contact_name}”。",
        )

    async def _plan_invoice_title(
        self,
        semantic: object,
        *,
        request: WorkflowTurnInput,
        workflow_id: str,
        runtime: WorkflowRuntimeContext,
    ) -> WorkflowActionPlan:
        invoice_title_source = semantic.invoice_title
        customer_id, customer_name = await self._resolve_customer(
            semantic,
            request=request,
            workflow_id=workflow_id,
            runtime=runtime,
        )
        set_default = invoice_title_source.set_default
        invoice_title = invoice_title_source.model_dump(
            exclude={"set_default"},
            exclude_none=True,
        )
        invoice_title = {key: value for key, value in invoice_title.items() if value != ""}
        missing_fields = business_rules.missing_invoice_title_fields(invoice_title)
        if missing_fields:
            raise self._needs_text(
                workflow_id=workflow_id,
                field="invoice_title_fields",
                business_action="provide_invoice_title_fields",
                title="补充发票抬头信息",
                prompt=(f"还需要补充:{business_rules.format_invoice_title_missing_fields(missing_fields)}。"),
            )
        title = str(invoice_title["title"])
        return self._confirmation_plan(
            workflow_id=workflow_id,
            action_type="create_invoice_title",
            payload={
                "customer_id": customer_id,
                "invoice_title": invoice_title,
                "set_default": set_default,
            },
            authorized_customer_ids=[customer_id],
            title="确认创建发票抬头",
            prompt=f"确认要为「{customer_name}」创建发票抬头“{title}”吗?",
            confirm_label="确认创建",
            completed_text=f"已为{customer_name}创建发票抬头“{title}”。",
            cancelled_text=f"已取消为{customer_name}创建发票抬头“{title}”。",
        )

    async def _plan_deployment_info(
        self,
        semantic: object,
        *,
        request: WorkflowTurnInput,
        workflow_id: str,
        runtime: WorkflowRuntimeContext,
    ) -> WorkflowActionPlan:
        customer_id, customer_name = await self._resolve_customer(
            semantic,
            request=request,
            workflow_id=workflow_id,
            runtime=runtime,
        )
        raw_deployment_info = getattr(semantic, "deployment_info", None)
        source = raw_deployment_info if isinstance(raw_deployment_info, dict) else {}
        deployment_info = {
            key: value
            for key in (
                "deployment_name",
                "server_address",
                "authorized_users",
                "is_default",
            )
            if (value := source.get(key)) is not None and value != ""
        }
        missing_fields = business_rules.missing_deployment_info_fields(deployment_info)
        if missing_fields:
            raise self._needs_text(
                workflow_id=workflow_id,
                field="deployment_info_fields",
                business_action="provide_deployment_info_fields",
                title="补充部署信息",
                prompt=(f"还需要补充:{business_rules.format_deployment_info_missing_fields(missing_fields)}。"),
            )
        deployment_info["customer_id"] = customer_id
        deployment_name = str(deployment_info["deployment_name"])
        return self._confirmation_plan(
            workflow_id=workflow_id,
            action_type="create_deployment_info",
            payload={"deployment_info": deployment_info},
            authorized_customer_ids=[customer_id],
            title="确认创建部署信息",
            prompt=f"确认要为「{customer_name}」创建部署信息“{deployment_name}”吗?",
            confirm_label="确认创建",
            completed_text=f"已为{customer_name}创建部署信息“{deployment_name}”。",
            cancelled_text=f"已取消为{customer_name}创建部署信息“{deployment_name}”。",
        )

    @staticmethod
    def _customer_create_payload(flat_customer: dict[str, object]) -> dict[str, object]:
        customer = {key: value for key, value in flat_customer.items() if not key.startswith("contact_")}
        if any(key in flat_customer for key in ("contact_name", "contact_phone", "contact_position", "contact_gender")):
            customer["primary_contact"] = {
                key: value
                for key, value in {
                    "name": flat_customer.get("contact_name"),
                    "mobile": flat_customer.get("contact_phone"),
                    "position": flat_customer.get("contact_position"),
                    "gender": flat_customer.get("contact_gender") or "0",
                    "email": flat_customer.get("contact_email"),
                }.items()
                if value is not None and value != ""
            }
        return customer

    async def _plan_customer_member(
        self,
        semantic: object,
        *,
        request: WorkflowTurnInput,
        workflow_id: str,
        runtime: WorkflowRuntimeContext,
    ) -> WorkflowActionPlan:
        customer_id, customer_name = await self._resolve_customer(
            semantic,
            request=request,
            workflow_id=workflow_id,
            runtime=runtime,
        )
        raw_member = getattr(semantic, "customer_member", None)
        member_source = raw_member if isinstance(raw_member, dict) else {}
        user_name_value = member_source.get("user_name")
        if not isinstance(user_name_value, str) or not user_name_value.strip():
            raise self._needs_text(
                workflow_id=workflow_id,
                field="customer_member_name",
                business_action="provide_customer_member_name",
                title="补充客户成员",
                prompt="请补充要添加的客户成员姓名。",
            )
        user_name = user_name_value.strip()
        selected_user_id = self._latest_supplement_metadata(
            request,
            "customer_member_user_id",
        )
        selected_user_name = self._latest_supplement_metadata(
            request,
            "customer_member_user_name",
        )
        if selected_user_name is not None:
            user_name = selected_user_name
        authorization = self._authorization(runtime)
        try:
            resolution = await self._customer_member_resolver.resolve(
                customer_id=customer_id,
                user_name=user_name,
                authorization=authorization,
                selected_user_id=selected_user_id,
            )
        except WorkflowResourceResolutionError as exc:
            raise WorkflowPlanningError(
                "WORKFLOW_CUSTOMER_MEMBER_RESOLUTION_FAILED",
                exc.message,
                retryable=exc.retryable,
            ) from exc

        if resolution.status == "ALREADY_MEMBER":
            resolved_name = resolution.user_name or user_name
            raise WorkflowPlanningError(
                "WORKFLOW_CUSTOMER_MEMBER_ALREADY_EXISTS",
                f"“{resolved_name}”已经是这个客户的负责人或成员,无需重复添加。",
            )
        if resolution.status == "NOT_FOUND":
            raise self._needs_text(
                workflow_id=workflow_id,
                field="customer_member_name",
                business_action="provide_customer_member_name",
                title="重新选择客户成员",
                prompt=f"未在当前客户的成员候选人中找到“{user_name}”,请输入准确姓名。",
            )
        if resolution.status == "AMBIGUOUS":
            suffix = workflow_id.removeprefix("wf_")
            raise WorkflowPlanningNeedsInput(
                WorkflowInteraction(
                    interaction_id=f"int_{suffix}_customer_member_choice",
                    interaction_type="choice",
                    business_action="select_customer_member",
                    title="选择客户成员",
                    prompt=f"找到多个名为“{user_name}”的候选成员,请选择具体人员。",
                    options=[
                        WorkflowInteractionOption(
                            value=candidate.user_id,
                            label=candidate.user_name,
                            description=(f"团队角色:{'、'.join(candidate.roles)}" if candidate.roles else None),
                            metadata={
                                "customer_member_user_id": candidate.user_id,
                                "customer_member_user_name": candidate.user_name,
                            },
                        )
                        for candidate in resolution.candidates
                    ],
                    selection_mode="single",
                    min_selections=1,
                    max_selections=1,
                    submit_label="继续",
                )
            )
        if not resolution.user_id or not resolution.user_name:
            raise WorkflowPlanningError(
                "WORKFLOW_CUSTOMER_MEMBER_RESOLUTION_INVALID",
                "客户成员解析结果无效。",
            )

        member_role = member_source.get("member_role") or "PRESALES"
        if member_role not in {"SALES", "PRESALES", "DELIVERY", "SUPPORT", "OTHER"}:
            raise WorkflowPlanningError(
                "WORKFLOW_CUSTOMER_MEMBER_ROLE_INVALID",
                "客户成员角色无效,请重新选择。",
            )
        access_level = member_source.get("access_level") or "VIEW"
        if access_level not in {"VIEW", "FOLLOW_UP", "EDIT"}:
            raise WorkflowPlanningError(
                "WORKFLOW_CUSTOMER_MEMBER_ACCESS_INVALID",
                "客户成员权限无效,请重新选择。",
            )
        member: dict[str, object] = {
            "user_id": resolution.user_id,
            "member_role": member_role,
            "access_level": access_level,
        }
        remark = member_source.get("remark")
        if isinstance(remark, str) and remark.strip():
            member["remark"] = remark.strip()

        return self._confirmation_plan(
            workflow_id=workflow_id,
            action_type="create_customer_member",
            payload={
                "customer_id": customer_id,
                "member": member,
            },
            authorized_customer_ids=[customer_id],
            title="确认添加客户成员",
            prompt=f"确认要为「{customer_name}」添加客户成员“{resolution.user_name}”吗?",
            confirm_label="确认添加",
            completed_text=f"已为{customer_name}添加客户成员“{resolution.user_name}”。",
            cancelled_text=f"已取消为{customer_name}添加客户成员“{resolution.user_name}”。",
        )

    async def _plan_opportunity(
        self,
        semantic: object,
        *,
        request: WorkflowTurnInput,
        workflow_id: str,
        runtime: WorkflowRuntimeContext,
        current_datetime: datetime,
    ) -> WorkflowActionPlan:
        customer_id, customer_name = await self._resolve_customer(
            semantic,
            request=request,
            workflow_id=workflow_id,
            runtime=runtime,
        )
        opportunity = self._semantic_opportunity_fields(
            semantic,
            current_datetime=current_datetime,
        )
        return await self._plan_opportunity_for_customer(
            customer_id=customer_id,
            customer_name=customer_name,
            opportunity=opportunity,
            request=request,
            workflow_id=workflow_id,
            runtime=runtime,
            require_confirmation=True,
        )

    async def _plan_opportunity_for_customer(
        self,
        *,
        customer_id: str,
        customer_name: str,
        opportunity: dict[str, object],
        request: WorkflowTurnInput,
        workflow_id: str,
        runtime: WorkflowRuntimeContext,
        require_confirmation: bool,
    ) -> WorkflowActionPlan:
        opportunity = dict(opportunity)
        opportunity.update(self._latest_opportunity_form_values(request))
        if opportunity.get("license_type") == "PERPETUAL":
            opportunity.pop("subscription_years", None)

        missing_fields = business_rules.missing_opportunity_fields(opportunity)
        if missing_fields:
            interaction_fields = [
                field
                for field in business_rules.opportunity_interaction_fields(missing_fields)
                if field != "procurement_method_id"
            ]
            raise WorkflowPlanningNeedsInput(
                WorkflowInteraction(
                    interaction_id=(f"int_{workflow_id.removeprefix('wf_')}_opportunity_fields"),
                    interaction_type="form",
                    business_action="collect_opportunity_fields",
                    title="补充商机信息",
                    prompt=(
                        f"请补充为「{customer_name}」创建商机所需的信息:"
                        f"{business_rules.format_opportunity_missing_fields(missing_fields)}。"
                    ),
                    fields=self._opportunity_interaction_fields(
                        interaction_fields,
                        defaults=opportunity,
                    ),
                    submit_label="继续",
                )
            )

        selected_method_id = self._latest_supplement_int_metadata(
            request,
            "procurement_method_id",
            business_action="select_opportunity_procurement_method",
        )
        authorization = self._authorization(runtime)
        try:
            resolution = await self._opportunity_procurement_method_resolver.resolve(
                customer_id=customer_id,
                authorization=authorization,
                selected_method_id=selected_method_id,
            )
        except WorkflowResourceResolutionError as exc:
            raise WorkflowPlanningError(
                "WORKFLOW_OPPORTUNITY_PROCUREMENT_RESOLUTION_FAILED",
                exc.message,
                retryable=exc.retryable,
            ) from exc

        if resolution.status in {"SELECTION_REQUIRED", "NOT_FOUND"} and resolution.candidates:
            raise WorkflowPlanningNeedsInput(
                self._opportunity_procurement_choice(
                    workflow_id=workflow_id,
                    customer_name=customer_name,
                    resolution=resolution,
                    stale_selection=resolution.status == "NOT_FOUND",
                )
            )
        if resolution.status == "NOT_FOUND":
            raise WorkflowPlanningError(
                "WORKFLOW_OPPORTUNITY_PROCUREMENT_UNAVAILABLE",
                "当前团队没有可用于创建商机的采购方式,请先完成采购方式配置。",
            )
        if resolution.method_id is None or resolution.method_name is None:
            raise WorkflowPlanningError(
                "WORKFLOW_OPPORTUNITY_PROCUREMENT_INVALID",
                "商机采购方式解析结果无效。",
            )

        payload: dict[str, object] = {
            "customer_id": customer_id,
            "total_amount": opportunity["total_amount"],
            "user_count": opportunity["user_count"],
            "license_type": opportunity["license_type"],
            "purchase_type": opportunity["purchase_type"],
            "expected_closing_date": opportunity["expected_closing_date"],
            "procurement_method_id": resolution.method_id,
        }
        for optional_field in ("subscription_years", "decision_maker_count"):
            value = opportunity.get(optional_field)
            if value is not None:
                payload[optional_field] = value
        summary = business_rules.format_opportunity_summary(payload)
        if not require_confirmation:
            return self._resume_commands_plan(
                workflow_id=workflow_id,
                commands=[
                    WorkflowCommand(
                        command_id="create_opportunity",
                        tool_name="create_opportunity",
                        payload={"opportunity": payload},
                        authorization_scope=WorkflowAuthorizationScope(customer_ids=[customer_id]),
                    )
                ],
                completed_text=f"已为{customer_name}创建商机。",
                cancelled_text="已取消创建商机。",
            )
        return self._confirmation_plan(
            workflow_id=workflow_id,
            action_type="create_opportunity",
            payload={"opportunity": payload},
            authorized_customer_ids=[customer_id],
            title="确认创建商机",
            prompt=(
                f"确认要为「{customer_name}」创建商机吗?{summary},"
                f"采购方式为“{resolution.method_name}”,预计成交日期为"
                f" {payload['expected_closing_date']}。"
            ),
            confirm_label="确认创建",
            completed_text=f"已为{customer_name}创建商机。",
            cancelled_text="已取消创建商机。",
        )

    async def _plan_opportunity_suggestion(
        self,
        request: WorkflowTurnInput,
        *,
        workflow_id: str,
        runtime: WorkflowRuntimeContext,
    ) -> WorkflowActionPlan:
        start = request.start
        if not isinstance(start, WorkflowOpportunitySuggestionStart):
            raise WorkflowPlanningError("WORKFLOW_START_INVALID", "工作流启动参数无效。")
        db = runtime.db
        if db is None:
            raise WorkflowPlanningError(
                "WORKFLOW_DATABASE_REQUIRED",
                "工作流暂时无法读取业务数据。",
                retryable=True,
            )
        job = (
            db.query(CustomerOpportunitySuggestionJob)
            .filter(
                CustomerOpportunitySuggestionJob.team_id == request.principal.team_id,
                CustomerOpportunitySuggestionJob.public_id == start.job_public_id,
            )
            .one_or_none()
        )
        if job is None:
            raise WorkflowPlanningError(
                "WORKFLOW_SUGGESTION_NOT_FOUND",
                "商机建议不存在或已失效。",
            )
        if start.action == "CANCEL":
            return self._terminal_cancel_plan(
                workflow_id=workflow_id,
                completed_text="已取消本次商机操作。",
                cancelled_text="已取消本次商机操作。",
            )
        if str(job.status) != CustomerActivitySuggestionJobStatus.COMPLETED.value:
            raise WorkflowPlanningError(
                "WORKFLOW_SUGGESTION_NOT_READY",
                "商机建议还在处理中，请稍后再试。",  # noqa: RUF001
                retryable=True,
            )
        result = job.result_json if isinstance(job.result_json, dict) else {}
        if str(result.get("decision")) != start.action:
            raise WorkflowPlanningError(
                "WORKFLOW_SUGGESTION_STALE",
                "这条商机建议已失效，无需重复执行。",  # noqa: RUF001
            )
        activity = (
            db.query(CustomerActivity)
            .filter(
                CustomerActivity.id == int(job.activity_id),
                CustomerActivity.team_id == request.principal.team_id,
            )
            .one_or_none()
        )
        if activity is None:
            raise WorkflowPlanningError(
                "WORKFLOW_SUGGESTION_SOURCE_DELETED",
                "源跟进已删除，本次商机操作不再执行。",  # noqa: RUF001
            )
        if (
            int(activity.activity_revision or 1) != int(job.activity_revision)
            or str(activity.submission_source) != CustomerActivitySubmissionSource.AGENT.value
            or activity.customer_id is None
        ):
            raise WorkflowPlanningError(
                "WORKFLOW_SUGGESTION_SOURCE_STALE",
                "源跟进已变化，本次商机操作不再执行。",  # noqa: RUF001
            )
        customer = (
            db.query(Customer)
            .filter(
                Customer.id == int(activity.customer_id),
                Customer.team_id == request.principal.team_id,
            )
            .one_or_none()
        )
        if customer is None:
            raise WorkflowPlanningError(
                "WORKFLOW_CUSTOMER_NOT_FOUND",
                "没有匹配客户。",
            )
        customer_id = str(customer.public_id)
        customer_name = str(customer.account_name).strip()
        cached_resolution = await self._validate_cached_customer(
            WorkflowResolvedCustomer(
                customer_id=customer_id,
                customer_name=customer_name,
                lookup_name=customer_name,
            ),
            runtime=runtime,
        )
        if (
            getattr(cached_resolution, "status", None) != "RESOLVED"
            or getattr(cached_resolution, "customer", None) is None
        ):
            raise WorkflowPlanningError("WORKFLOW_CUSTOMER_NOT_FOUND", "没有匹配客户。")
        resolved_customer = cached_resolution.customer
        customer_id = resolved_customer.customer_id
        customer_name = resolved_customer.customer_name
        suggestion = result.get("suggestion")
        if not isinstance(suggestion, dict):
            raise WorkflowPlanningError("WORKFLOW_SUGGESTION_INVALID", "商机建议结果无效。")
        if start.action == "CREATE_OPPORTUNITY":
            execution_payload = suggestion.get("execution_payload")
            if not isinstance(execution_payload, dict):
                execution_payload = {}
            allowed = {
                "total_amount",
                "user_count",
                "license_type",
                "subscription_years",
                "purchase_type",
                "decision_maker_count",
                "expected_closing_date",
            }
            try:
                opportunity = self._validated_opportunity_form_values(
                    {key: value for key, value in execution_payload.items() if key in allowed}
                )
            except WorkflowPlanningError as exc:
                raise WorkflowPlanningError(
                    "WORKFLOW_SUGGESTION_INVALID",
                    "商机建议中的业务字段无效。",
                ) from exc
            return await self._plan_opportunity_for_customer(
                customer_id=customer_id,
                customer_name=customer_name,
                opportunity=opportunity,
                request=request,
                workflow_id=workflow_id,
                runtime=runtime,
                require_confirmation=False,
            )

        execution_payload = suggestion.get("execution_payload")
        if not isinstance(execution_payload, dict):
            execution_payload = {}
        opportunity_id = suggestion.get("related_object_id") or execution_payload.get("opportunity_id")
        stage_template_id = execution_payload.get("stage_template_id")
        if not isinstance(opportunity_id, str) or not opportunity_id.strip():
            raise WorkflowPlanningError("WORKFLOW_SUGGESTION_INVALID", "商机建议缺少目标商机。")
        try:
            stage_template_id = int(stage_template_id)
        except (TypeError, ValueError) as exc:
            raise WorkflowPlanningError("WORKFLOW_SUGGESTION_INVALID", "商机建议缺少目标阶段。") from exc
        try:
            resolution = await self._opportunity_stage_resolver.resolve(
                customer_id=customer_id,
                authorization=self._authorization(runtime),
                opportunity_id=opportunity_id,
                opportunity_reference_text=None,
                target_stage_name=None,
                selected_opportunity_id=opportunity_id,
                selected_stage_id=stage_template_id,
            )
        except WorkflowResourceResolutionError as exc:
            raise WorkflowPlanningError(
                "WORKFLOW_OPPORTUNITY_STAGE_RESOLUTION_FAILED",
                exc.message,
                retryable=exc.retryable,
            ) from exc
        if resolution.status != "RESOLVED" or resolution.opportunity is None or not resolution.steps:
            # The suggestion was evaluated against an earlier opportunity state.
            # If that state is no longer current, this turn is a successful no-op:
            # do not overwrite the newer state, retry the mutation, or prompt the
            # user to reconcile a race they did not cause.
            return self._terminal_skip_plan(
                workflow_id=workflow_id,
                reason="opportunity_state_changed",
            )
        commands = [
            WorkflowCommand(
                command_id=f"move_opportunity_stage_{index}",
                tool_name="move_opportunity_stage",
                payload={
                    "opportunity_id": resolution.opportunity.opportunity_id,
                    "stage_template_id": step.stage_template_id,
                },
                authorization_scope=WorkflowAuthorizationScope(customer_ids=[customer_id]),
            )
            for index, step in enumerate(resolution.steps, start=1)
        ]
        return self._resume_commands_plan(
            workflow_id=workflow_id,
            commands=commands,
            completed_text=(
                f"已将商机“{resolution.opportunity.opportunity_name}”推进到“{resolution.target_stage.stage_name}”。"
            ),
            cancelled_text="已取消推进商机。",
        )

    async def _plan_opportunity_stage_transition(
        self,
        semantic: object,
        *,
        request: WorkflowTurnInput,
        workflow_id: str,
        runtime: WorkflowRuntimeContext,
        current_datetime: datetime,
        user_message: str,
    ) -> WorkflowActionPlan:
        customer_id, customer_name = await self._resolve_customer(
            semantic,
            request=request,
            workflow_id=workflow_id,
            runtime=runtime,
        )
        transition = getattr(semantic, "opportunity_stage_transition", None)
        opportunity_id = self._optional_non_blank_text(getattr(transition, "opportunity_id", None))
        opportunity_reference_text = self._optional_non_blank_text(
            getattr(transition, "opportunity_reference_text", None)
        )
        target_stage_name = self._optional_non_blank_text(getattr(transition, "target_stage_name", None))
        selected_opportunity_id = self._latest_supplement_metadata_for_action(
            request,
            "opportunity_id",
            business_action="select_opportunity_for_stage_transition",
        )
        selected_stage_id = self._latest_supplement_int_metadata(
            request,
            "stage_template_id",
            business_action="select_opportunity_stage",
        )
        try:
            resolution = await self._opportunity_stage_resolver.resolve(
                customer_id=customer_id,
                authorization=self._authorization(runtime),
                opportunity_id=opportunity_id,
                opportunity_reference_text=opportunity_reference_text,
                target_stage_name=target_stage_name,
                selected_opportunity_id=selected_opportunity_id,
                selected_stage_id=selected_stage_id,
            )
        except WorkflowResourceResolutionError as exc:
            raise WorkflowPlanningError(
                "WORKFLOW_OPPORTUNITY_STAGE_RESOLUTION_FAILED",
                exc.message,
                retryable=exc.retryable,
            ) from exc

        if resolution.status == "OPPORTUNITY_SELECTION_REQUIRED":
            candidate_rows = [
                {
                    "id": index,
                    "name": candidate.opportunity_name,
                    "current_stage": candidate.current_stage_name,
                }
                for index, candidate in enumerate(resolution.opportunity_candidates, start=1)
            ]
            ranked = await self._select_semantic_resource(
                runtime=runtime,
                user_message=user_message,
                resource_kind="opportunity",
                action_name="MOVE_OPPORTUNITY_STAGE",
                target={
                    "customer_name": customer_name,
                    "opportunity_reference": opportunity_reference_text,
                    "target_stage": target_stage_name,
                },
                candidates=candidate_rows,
                team_id=request.principal.team_id,
                current_date=current_datetime.date(),
            )
            if ranked is not None:
                ranked_index = int(ranked["id"]) - 1
                selected = resolution.opportunity_candidates[ranked_index]
                try:
                    resolution = await self._opportunity_stage_resolver.resolve(
                        customer_id=customer_id,
                        authorization=self._authorization(runtime),
                        opportunity_id=opportunity_id,
                        opportunity_reference_text=opportunity_reference_text,
                        target_stage_name=target_stage_name,
                        selected_opportunity_id=selected.opportunity_id,
                        selected_stage_id=selected_stage_id,
                    )
                except WorkflowResourceResolutionError as exc:
                    raise WorkflowPlanningError(
                        "WORKFLOW_OPPORTUNITY_STAGE_RESOLUTION_FAILED",
                        exc.message,
                        retryable=exc.retryable,
                    ) from exc
            if resolution.status == "OPPORTUNITY_SELECTION_REQUIRED":
                raise WorkflowPlanningNeedsInput(
                    self._opportunity_stage_opportunity_choice(
                        workflow_id=workflow_id,
                        customer_name=customer_name,
                        resolution=resolution,
                    )
                )
        if resolution.status == "STAGE_SELECTION_REQUIRED":
            candidate_rows = [
                {"id": index, "name": candidate.stage_name}
                for index, candidate in enumerate(resolution.stage_candidates, start=1)
            ]
            ranked = await self._select_semantic_resource(
                runtime=runtime,
                user_message=user_message,
                resource_kind="opportunity_stage",
                action_name="MOVE_OPPORTUNITY_STAGE",
                target={
                    "customer_name": customer_name,
                    "opportunity_name": (
                        resolution.opportunity.opportunity_name
                        if resolution.opportunity is not None
                        else None
                    ),
                    "target_stage": target_stage_name,
                },
                candidates=candidate_rows,
                team_id=request.principal.team_id,
                current_date=current_datetime.date(),
            )
            if ranked is not None and resolution.opportunity is not None:
                ranked_index = int(ranked["id"]) - 1
                selected = resolution.stage_candidates[ranked_index]
                try:
                    resolution = await self._opportunity_stage_resolver.resolve(
                        customer_id=customer_id,
                        authorization=self._authorization(runtime),
                        opportunity_id=resolution.opportunity.opportunity_id,
                        opportunity_reference_text=None,
                        target_stage_name=target_stage_name,
                        selected_opportunity_id=resolution.opportunity.opportunity_id,
                        selected_stage_id=selected.stage_template_id,
                    )
                except WorkflowResourceResolutionError as exc:
                    raise WorkflowPlanningError(
                        "WORKFLOW_OPPORTUNITY_STAGE_RESOLUTION_FAILED",
                        exc.message,
                        retryable=exc.retryable,
                    ) from exc
            if resolution.status == "STAGE_SELECTION_REQUIRED":
                raise WorkflowPlanningNeedsInput(
                    self._opportunity_stage_choice(
                        workflow_id=workflow_id,
                        resolution=resolution,
                    )
                )
        if resolution.status == "NOT_FOUND":
            raise WorkflowPlanningError(
                "WORKFLOW_OPPORTUNITY_STAGE_NOT_FOUND",
                "没有找到可按当前要求推进的商机阶段。",
            )
        if resolution.opportunity is None or resolution.target_stage is None or not resolution.steps:
            raise WorkflowPlanningError(
                "WORKFLOW_OPPORTUNITY_STAGE_RESOLUTION_INVALID",
                "商机阶段解析结果无效。",
            )

        commands = [
            WorkflowCommand(
                command_id=f"move_opportunity_stage_{index}",
                tool_name="move_opportunity_stage",
                payload={
                    "opportunity_id": resolution.opportunity.opportunity_id,
                    "stage_template_id": step.stage_template_id,
                },
                authorization_scope=WorkflowAuthorizationScope(customer_ids=[customer_id]),
            )
            for index, step in enumerate(resolution.steps, start=1)
        ]
        stage_path = "、".join(f"“{step.stage_name}”" for step in resolution.steps)
        return self._confirmation_commands_plan(
            workflow_id=workflow_id,
            business_action="move_opportunity_stage",
            commands=commands,
            title="确认推进商机阶段",
            prompt=f"确认要将商机“{resolution.opportunity.opportunity_name}”推进到{stage_path}吗?",
            confirm_label="确认推进",
            completed_text=(
                f"已将商机“{resolution.opportunity.opportunity_name}”推进到“{resolution.target_stage.stage_name}”。"
            ),
            cancelled_text=f"已取消推进商机“{resolution.opportunity.opportunity_name}”。",
        )

    async def _plan_follow_up_task_transition(
        self,
        semantic: object,
        *,
        request: WorkflowTurnInput,
        workflow_id: str,
        runtime: WorkflowRuntimeContext,
        current_datetime: datetime,
    ) -> WorkflowActionPlan:
        transition = getattr(semantic, "follow_up_task_transition", None)
        action = self._optional_non_blank_text(getattr(transition, "action", None))
        if action not in {"complete", "cancel", "postpone"}:
            raise WorkflowPlanningError(
                "WORKFLOW_FOLLOW_UP_TASK_ACTION_UNSUPPORTED",
                "跟进任务只支持完成、取消或延期。",
            )
        task_id = self._optional_non_blank_text(getattr(transition, "task_id", None))
        task_reference_text = self._optional_non_blank_text(
            getattr(transition, "task_reference_text", None)
        )
        selected_task_id = self._latest_supplement_metadata_for_action(
            request,
            "task_id",
            business_action="select_follow_up_task",
        )
        try:
            resolution = await self._follow_up_task_resolver.resolve(
                authorization=self._authorization(runtime),
                user_id=request.principal.user_id,
                task_id=task_id,
                task_reference_text=task_reference_text,
                selected_task_id=selected_task_id,
            )
        except WorkflowResourceResolutionError as exc:
            raise WorkflowPlanningError(
                "WORKFLOW_FOLLOW_UP_TASK_RESOLUTION_FAILED",
                exc.message,
                retryable=exc.retryable,
            ) from exc

        task = resolution.task
        if resolution.status == "SELECTION_REQUIRED":
            candidate_rows = [
                {
                    "id": index,
                    "name": candidate.title,
                    "customer_name": candidate.customer_name,
                    "due_at": candidate.due_at,
                }
                for index, candidate in enumerate(resolution.candidates, start=1)
            ]
            ranked = await self._select_semantic_resource(
                runtime=runtime,
                user_message=self._planning_text(request.start.text, request.supplements),
                resource_kind="follow_up_task",
                action_name=f"FOLLOW_UP_TASK_{action.upper()}",
                target={
                    "task_reference": task_reference_text,
                    "requested_action": action,
                },
                candidates=candidate_rows,
                team_id=request.principal.team_id,
                current_date=current_datetime.date(),
            )
            if ranked is not None:
                selected_candidate = resolution.candidates[int(ranked["id"]) - 1]
                # The LLM only chooses an ordinal from the snapshot. Re-read
                # that task by its server-owned public ID before planning any
                # mutation so ownership, open status, and freshness are still
                # authoritative at the decision boundary.
                try:
                    resolution = await self._follow_up_task_resolver.resolve(
                        authorization=self._authorization(runtime),
                        user_id=request.principal.user_id,
                        selected_task_id=selected_candidate.task_id,
                    )
                except WorkflowResourceResolutionError as exc:
                    raise WorkflowPlanningError(
                        "WORKFLOW_FOLLOW_UP_TASK_RESOLUTION_FAILED",
                        exc.message,
                        retryable=exc.retryable,
                    ) from exc
                task = resolution.task
            else:
                raise WorkflowPlanningNeedsInput(
                    self._follow_up_task_choice(
                        workflow_id=workflow_id,
                        resolution=resolution,
                        stale_selection=selected_task_id is not None,
                    )
                )
        if resolution.status == "NOT_FOUND" or task is None:
            raise WorkflowPlanningError(
                "WORKFLOW_FOLLOW_UP_TASK_NOT_FOUND",
                "没有找到仍可更新的本人待跟进任务。",
            )

        proposed_due_at: str | None = None
        if action == "postpone":
            proposed_due_at = self._temporal_resolver.resolve_follow_up_time(
                getattr(transition, "proposed_due_at", None),
                base_datetime=current_datetime,
            )
            if proposed_due_at is None:
                raise self._needs_text(
                    workflow_id=workflow_id,
                    field="follow_up_task_due_at",
                    business_action="collect_follow_up_task_postpone_due_at",
                    title="补充延期时间",
                    prompt=f"请说明要将跟进任务“{task.title}”延期到什么时间。",
                )

        reason = self._optional_non_blank_text(getattr(transition, "reason", None))
        action_label = {
            "complete": "标记为完成",
            "cancel": "取消",
            "postpone": f"延期到 {proposed_due_at}",
        }[action]
        customer_prefix = f"{task.customer_name}的" if task.customer_name else ""
        completed_text = {
            "complete": f"已将跟进任务“{task.title}”标记为完成。",
            "cancel": f"已取消跟进任务“{task.title}”。",
            "postpone": f"已将跟进任务“{task.title}”延期到 {proposed_due_at}。",
        }[action]
        return self._confirmation_plan(
            workflow_id=workflow_id,
            action_type="transition_follow_up_task",
            payload={
                "task_id": task.task_id,
                "action": action,
                "proposed_due_at": proposed_due_at,
                "reason": reason,
            },
            authorized_customer_ids=([task.customer_id] if task.customer_id is not None else []),
            title="确认更新跟进任务",
            prompt=f"确认要将{customer_prefix}跟进任务“{task.title}”{action_label}吗?",
            confirm_label="确认更新",
            completed_text=completed_text,
            cancelled_text=f"已取消更新跟进任务“{task.title}”。",
        )

    @staticmethod
    def _follow_up_task_choice(
        *,
        workflow_id: str,
        resolution: FollowUpTaskResolution,
        stale_selection: bool,
    ) -> WorkflowInteraction:
        prompt = (
            "之前选择的跟进任务已失效,请重新选择。"
            if stale_selection
            else "找到多个本人待跟进任务,请选择要更新的任务。"
        )
        return WorkflowInteraction(
            interaction_id=f"int_{workflow_id.removeprefix('wf_')}_follow_up_task",
            interaction_type="choice",
            business_action="select_follow_up_task",
            title="选择跟进任务",
            prompt=prompt,
            options=[
                WorkflowInteractionOption(
                    value=candidate.task_id,
                    label=(
                        f"{candidate.customer_name} · {candidate.title}"
                        if candidate.customer_name
                        else candidate.title
                    ),
                    description=candidate.due_at,
                    metadata={
                        "task_id": candidate.task_id,
                        "task_title": candidate.title,
                    },
                )
                for candidate in resolution.candidates
            ],
            selection_mode="single",
            min_selections=1,
            max_selections=1,
            submit_label="继续",
        )

    def _semantic_opportunity_fields(
        self,
        semantic: object,
        *,
        current_datetime: datetime,
    ) -> dict[str, object]:
        opportunity = getattr(semantic, "opportunity", None)
        if opportunity is None:
            return {}
        values: dict[str, object] = {}
        total_amount = getattr(opportunity, "total_amount", None)
        if isinstance(total_amount, (int, float)) and not isinstance(total_amount, bool):
            values["total_amount"] = float(total_amount)
        for field_name in ("user_count", "subscription_years", "decision_maker_count"):
            value = getattr(opportunity, field_name, None)
            if isinstance(value, int) and not isinstance(value, bool):
                values[field_name] = value
        license_type = getattr(opportunity, "license_type", None)
        if license_type in {"SUBSCRIPTION", "PERPETUAL"}:
            values["license_type"] = license_type
        purchase_type = getattr(opportunity, "purchase_type", None)
        if purchase_type in {"NEW", "RENEWAL", "EXPANSION"}:
            values["purchase_type"] = purchase_type
        expected_closing_date = self._temporal_resolver.resolve_date(
            getattr(opportunity, "expected_closing_date", None),
            base_datetime=current_datetime,
        )
        if expected_closing_date is not None:
            values["expected_closing_date"] = expected_closing_date
        return values

    @staticmethod
    def _latest_opportunity_form_values(
        request: WorkflowTurnInput,
    ) -> dict[str, object]:
        for supplement in reversed(request.supplements):
            if supplement.metadata.get("business_action") != "collect_opportunity_fields":
                continue
            raw_values = supplement.metadata.get("form_values")
            if not isinstance(raw_values, dict):
                raise WorkflowPlanningError(
                    "WORKFLOW_OPPORTUNITY_FIELDS_INVALID",
                    "提交的商机信息无效,请重新填写。",
                )
            return CRMWorkflowPlanner._validated_opportunity_form_values(raw_values)
        return {}

    @staticmethod
    def _validated_opportunity_form_values(
        raw_values: dict[str, object],
    ) -> dict[str, object]:
        allowed_fields = {
            "total_amount",
            "user_count",
            "license_type",
            "subscription_years",
            "purchase_type",
            "decision_maker_count",
            "expected_closing_date",
        }
        if set(raw_values) - allowed_fields:
            raise WorkflowPlanningError(
                "WORKFLOW_OPPORTUNITY_FIELDS_INVALID",
                "提交的商机信息包含未授权字段。",
            )
        values: dict[str, object] = {}
        total_amount = raw_values.get("total_amount")
        if total_amount is not None:
            if not isinstance(total_amount, (int, float)) or isinstance(total_amount, bool) or total_amount <= 0:
                raise WorkflowPlanningError(
                    "WORKFLOW_OPPORTUNITY_FIELDS_INVALID",
                    "预计成交金额必须大于 0。",
                )
            values["total_amount"] = float(total_amount)
        for field_name in ("user_count", "subscription_years", "decision_maker_count"):
            value = raw_values.get(field_name)
            if value is None:
                continue
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise WorkflowPlanningError(
                    "WORKFLOW_OPPORTUNITY_FIELDS_INVALID",
                    "商机人数和年限必须为正整数。",
                )
            values[field_name] = value
        license_type = raw_values.get("license_type")
        if license_type is not None:
            if license_type not in {"SUBSCRIPTION", "PERPETUAL"}:
                raise WorkflowPlanningError(
                    "WORKFLOW_OPPORTUNITY_FIELDS_INVALID",
                    "授权模式无效。",
                )
            values["license_type"] = license_type
        purchase_type = raw_values.get("purchase_type")
        if purchase_type is not None:
            if purchase_type not in {"NEW", "RENEWAL", "EXPANSION"}:
                raise WorkflowPlanningError(
                    "WORKFLOW_OPPORTUNITY_FIELDS_INVALID",
                    "采购类型无效。",
                )
            values["purchase_type"] = purchase_type
        expected_closing_date = raw_values.get("expected_closing_date")
        if expected_closing_date is not None:
            if not isinstance(expected_closing_date, str):
                raise WorkflowPlanningError(
                    "WORKFLOW_OPPORTUNITY_FIELDS_INVALID",
                    "预计成交日期无效。",
                )
            try:
                date.fromisoformat(expected_closing_date)
            except ValueError as exc:
                raise WorkflowPlanningError(
                    "WORKFLOW_OPPORTUNITY_FIELDS_INVALID",
                    "预计成交日期无效。",
                ) from exc
            values["expected_closing_date"] = expected_closing_date
        return values

    @staticmethod
    def _opportunity_interaction_fields(
        field_names: list[str],
        *,
        defaults: dict[str, object],
    ) -> list[WorkflowInteractionField]:
        fields: list[WorkflowInteractionField] = []
        for field_name in field_names:
            required = not (field_name == "subscription_years" and "license_type" in field_names)
            if field_name == "license_type":
                fields.append(
                    WorkflowInteractionField(
                        key=field_name,
                        label="授权模式",
                        field_type="select",
                        required=required,
                        default_value=defaults.get(field_name),
                        options=[
                            WorkflowInteractionOption(
                                value="SUBSCRIPTION",
                                label="订阅制",
                            ),
                            WorkflowInteractionOption(
                                value="PERPETUAL",
                                label="买断制",
                            ),
                        ],
                    )
                )
                continue
            if field_name == "purchase_type":
                fields.append(
                    WorkflowInteractionField(
                        key=field_name,
                        label="采购类型",
                        field_type="select",
                        required=required,
                        default_value=defaults.get(field_name),
                        options=[
                            WorkflowInteractionOption(value="NEW", label="新购"),
                            WorkflowInteractionOption(value="RENEWAL", label="续购"),
                            WorkflowInteractionOption(value="EXPANSION", label="增购"),
                        ],
                    )
                )
                continue
            if field_name == "expected_closing_date":
                fields.append(
                    WorkflowInteractionField(
                        key=field_name,
                        label="预计成交日期",
                        field_type="date",
                        required=required,
                        default_value=defaults.get(field_name),
                    )
                )
                continue
            label = {
                "total_amount": "预计成交金额",
                "user_count": "采购用户数",
                "subscription_years": "订阅年限",
                "decision_maker_count": "采购决策人数",
            }[field_name]
            fields.append(
                WorkflowInteractionField(
                    key=field_name,
                    label=label,
                    field_type="number",
                    required=required,
                    default_value=defaults.get(field_name),
                    minimum=0.01 if field_name == "total_amount" else 1,
                )
            )
        return fields

    @staticmethod
    def _opportunity_procurement_choice(
        *,
        workflow_id: str,
        customer_name: str,
        resolution: ProcurementMethodResolution,
        stale_selection: bool,
    ) -> WorkflowInteraction:
        suffix = workflow_id.removeprefix("wf_")
        prompt = (
            "之前选择的采购方式已失效,请重新选择。"
            if stale_selection
            else f"「{customer_name}」未配置默认采购方式,请选择本次商机的采购方式。"
        )
        return WorkflowInteraction(
            interaction_id=f"int_{suffix}_opportunity_procurement_method",
            interaction_type="choice",
            business_action="select_opportunity_procurement_method",
            title="选择采购方式",
            prompt=prompt,
            options=[
                WorkflowInteractionOption(
                    value=str(candidate.method_id),
                    label=candidate.method_name,
                    description=f"编码:{candidate.method_code}",
                    metadata={
                        "procurement_method_id": candidate.method_id,
                        "procurement_method_name": candidate.method_name,
                    },
                )
                for candidate in resolution.candidates
            ],
            selection_mode="single",
            min_selections=1,
            max_selections=1,
            submit_label="继续",
        )

    @staticmethod
    def _opportunity_stage_opportunity_choice(
        *,
        workflow_id: str,
        customer_name: str,
        resolution: OpportunityStageResolution,
    ) -> WorkflowInteraction:
        suffix = workflow_id.removeprefix("wf_")
        return WorkflowInteraction(
            interaction_id=f"int_{suffix}_opportunity_stage_opportunity",
            interaction_type="choice",
            business_action="select_opportunity_for_stage_transition",
            title="选择要推进的商机",
            prompt=f"「{customer_name}」有多个可推进的商机,请选择一个。",
            options=[
                WorkflowInteractionOption(
                    value=candidate.opportunity_id,
                    label=candidate.opportunity_name,
                    description=(
                        f"当前阶段:{candidate.current_stage_name}"
                        if candidate.current_stage_name
                        else "尚未进入采购阶段"
                    ),
                    metadata={
                        "opportunity_id": candidate.opportunity_id,
                        "opportunity_name": candidate.opportunity_name,
                    },
                )
                for candidate in resolution.opportunity_candidates
            ],
            selection_mode="single",
            min_selections=1,
            max_selections=1,
            submit_label="继续",
        )

    @staticmethod
    def _opportunity_stage_choice(
        *,
        workflow_id: str,
        resolution: OpportunityStageResolution,
    ) -> WorkflowInteraction:
        suffix = workflow_id.removeprefix("wf_")
        opportunity_name = resolution.opportunity.opportunity_name if resolution.opportunity else "当前商机"
        return WorkflowInteraction(
            interaction_id=f"int_{suffix}_opportunity_stage",
            interaction_type="choice",
            business_action="select_opportunity_stage",
            title="选择目标阶段",
            prompt=f"请选择商机“{opportunity_name}”要推进到的目标阶段。",
            options=[
                WorkflowInteractionOption(
                    value=str(candidate.stage_template_id),
                    label=candidate.stage_name,
                    metadata={
                        "stage_template_id": candidate.stage_template_id,
                        "stage_name": candidate.stage_name,
                    },
                )
                for candidate in resolution.stage_candidates
            ],
            selection_mode="single",
            min_selections=1,
            max_selections=1,
            submit_label="继续",
        )

    async def _plan_follow_up_confirmation_case(
        self,
        request: WorkflowTurnInput,
        *,
        workflow_id: str,
        runtime: WorkflowRuntimeContext,
    ) -> WorkflowActionPlan:
        start = request.start
        if not isinstance(start, WorkflowResourceStart) or start.workflow != "follow_up_task_confirmation":
            raise WorkflowPlanningError("WORKFLOW_START_INVALID", "工作流启动参数无效。")
        resolver = self._follow_up_confirmation_case_resolver
        authorization = runtime.authorization
        if resolver is None or not isinstance(authorization, str) or not authorization:
            raise WorkflowPlanningError(
                "WORKFLOW_RESOURCE_RESOLVER_UNAVAILABLE",
                "待确认事项暂时无法读取, 请稍后重试。",
                retryable=True,
            )
        try:
            resolution = await resolver.resolve(
                authorization=authorization,
                user_id=request.principal.user_id,
                case_id=start.resource_id,
            )
        except WorkflowResourceResolutionError as exc:
            raise WorkflowPlanningError(
                "WORKFLOW_RESOURCE_RESOLUTION_FAILED",
                exc.message,
                retryable=exc.retryable,
            ) from exc
        case = resolution.case
        if (
            resolution.status != "RESOLVED"
            or case is None
            or case.case_id != start.resource_id
            or case.owner_id != str(request.principal.user_id)
            or case.status != "PENDING"
        ):
            raise WorkflowPlanningError(
                "WORKFLOW_RESOURCE_NOT_FOUND",
                "待确认事项不存在或已处理。",
            )
        interaction_id = f"int_{workflow_id.removeprefix('wf_')}_follow_up_confirmation_case"
        if not request.supplements:
            raise WorkflowPlanningNeedsInput(
                WorkflowInteraction(
                    interaction_id=interaction_id,
                    interaction_type="choice",
                    business_action="resolve_follow_up_task_confirmation_case",
                    title="确认跟进任务状态",
                    prompt=case.question_text,
                    options=[
                        WorkflowInteractionOption(value="已完成", label="标记完成"),
                        WorkflowInteractionOption(value="先放着", label="保持未完成"),
                        WorkflowInteractionOption(value="不管了", label="不再跟进"),
                    ],
                    selection_mode="single",
                    min_selections=1,
                    max_selections=1,
                    submit_on_select=True,
                    submit_label="提交",
                )
            )
        if len(request.supplements) != 1:
            raise WorkflowPlanningError("WORKFLOW_SUPPLEMENT_INVALID", "工作流回复无效。")
        supplement = request.supplements[0]
        if (
            supplement.metadata.get("business_action")
            != "resolve_follow_up_task_confirmation_case"
            or supplement.metadata.get("interaction_id") != interaction_id
            or not supplement.content.strip()
        ):
            raise WorkflowPlanningError("WORKFLOW_SUPPLEMENT_INVALID", "工作流回复无效。")
        customer_ids = [case.customer_id] if case.customer_id is not None else []
        return WorkflowActionPlan(
            action_id=f"act_{workflow_id.removeprefix('wf_')}",
            execution_authorization="RESUME_AUTHORIZED",
            commands=[
                WorkflowCommand(
                    command_id="resolve_follow_up_task_confirmation_case",
                    tool_name="resolve_follow_up_task_confirmation_case",
                    payload={
                        "case_id": start.resource_id,
                        "reply_text": supplement.content.strip(),
                    },
                    authorization_scope=WorkflowAuthorizationScope(customer_ids=customer_ids),
                )
            ],
            completed_text="已处理该跟进任务确认事项。",
            cancelled_text="已取消处理该跟进任务确认事项。",
        )

    @staticmethod
    def _auto_execute_plan(
        *,
        workflow_id: str,
        action_type: str,
        payload: dict[str, object],
        authorized_customer_ids: list[str],
        confidence: float,
        completed_text: str,
        cancelled_text: str,
    ) -> WorkflowActionPlan:
        suffix = workflow_id.removeprefix("wf_")
        return WorkflowActionPlan(
            action_id=f"act_{suffix}",
            execution_authorization="AUTO_EXECUTE_AUTHORIZED",
            risk_level="LOW",
            authorization_confidence=confidence,
            commands=[
                WorkflowCommand(
                    command_id=action_type,
                    tool_name=action_type,
                    payload=payload,
                    authorization_scope=WorkflowAuthorizationScope(
                        customer_ids=authorized_customer_ids,
                    ),
                )
            ],
            completed_text=completed_text,
            cancelled_text=cancelled_text,
        )

    @staticmethod
    def _resume_commands_plan(
        *,
        workflow_id: str,
        commands: list[WorkflowCommand],
        completed_text: str,
        cancelled_text: str,
    ) -> WorkflowActionPlan:
        return WorkflowActionPlan(
            action_id=f"act_{workflow_id.removeprefix('wf_')}",
            execution_authorization="RESUME_AUTHORIZED",
            commands=commands,
            completed_text=completed_text,
            cancelled_text=cancelled_text,
        )

    @staticmethod
    def _terminal_cancel_plan(
        *,
        workflow_id: str,
        completed_text: str,
        cancelled_text: str,
    ) -> WorkflowActionPlan:
        return WorkflowActionPlan(
            action_id=f"act_{workflow_id.removeprefix('wf_')}",
            execution_authorization="RESUME_AUTHORIZED",
            terminal_outcome="CANCELLED",
            completed_text=completed_text,
            cancelled_text=cancelled_text,
        )

    @staticmethod
    def _terminal_skip_plan(
        *,
        workflow_id: str,
        reason: str,
    ) -> WorkflowActionPlan:
        """Build a terminal no-op plan without a user-facing business message."""
        return WorkflowActionPlan(
            action_id=f"act_{workflow_id.removeprefix('wf_')}",
            execution_authorization="RESUME_AUTHORIZED",
            terminal_outcome="SKIPPED",
            terminal_reason=reason,
        )

    @classmethod
    def _confirmation_plan(
        cls,
        *,
        workflow_id: str,
        action_type: str,
        payload: dict[str, object],
        authorized_customer_ids: list[str],
        title: str,
        prompt: str,
        confirm_label: str,
        completed_text: str,
        cancelled_text: str,
    ) -> WorkflowActionPlan:
        return cls._confirmation_commands_plan(
            workflow_id=workflow_id,
            business_action=action_type,
            commands=[
                WorkflowCommand(
                    command_id=action_type,
                    tool_name=action_type,
                    payload=payload,
                    authorization_scope=WorkflowAuthorizationScope(
                        customer_ids=authorized_customer_ids,
                    ),
                )
            ],
            title=title,
            prompt=prompt,
            confirm_label=confirm_label,
            completed_text=completed_text,
            cancelled_text=cancelled_text,
        )

    @staticmethod
    def _confirmation_commands_plan(
        *,
        workflow_id: str,
        business_action: str,
        commands: list[WorkflowCommand],
        title: str,
        prompt: str,
        confirm_label: str,
        completed_text: str,
        cancelled_text: str,
    ) -> WorkflowActionPlan:
        suffix = workflow_id.removeprefix("wf_")
        return WorkflowActionPlan(
            action_id=f"act_{suffix}",
            execution_authorization="CONFIRMATION_REQUIRED",
            commands=commands,
            interaction=WorkflowInteraction(
                interaction_id=f"int_{suffix}",
                interaction_type="confirmation",
                business_action=business_action,
                title=title,
                prompt=prompt,
                options=[
                    WorkflowInteractionOption(value="confirm", label=confirm_label),
                    WorkflowInteractionOption(value="cancel", label="取消"),
                ],
                selection_mode="single",
                submit_on_select=True,
                submit_label="确认",
            ),
            completed_text=completed_text,
            cancelled_text=cancelled_text,
        )

    @staticmethod
    def _needs_text(
        *,
        workflow_id: str,
        field: str,
        business_action: str,
        title: str,
        prompt: str,
        checkpoint_request: WorkflowTurnInput | None = None,
    ) -> WorkflowPlanningNeedsInput:
        return WorkflowPlanningNeedsInput(
            WorkflowInteraction(
                interaction_id=f"int_{workflow_id.removeprefix('wf_')}_{field}",
                interaction_type="text_input",
                business_action=business_action,
                title=title,
                prompt=prompt,
                allow_blank=False,
                submit_label="继续",
            ),
            checkpoint_request=checkpoint_request,
        )

    @staticmethod
    def _cache_semantic_snapshot(
        request: WorkflowTurnInput,
        semantic: object,
    ) -> WorkflowTurnInput:
        if not isinstance(request.start, WorkflowTextStart):
            return request
        if not hasattr(semantic, "model_dump"):
            return request
        snapshot = semantic.model_dump(mode="json")
        return request.model_copy(
            update={
                "start": request.start.model_copy(
                    update={"semantic_snapshot": snapshot}
                )
            }
        )

    @classmethod
    def _semantic_for_request(cls, request: WorkflowTurnInput) -> object | None:
        if not isinstance(request.start, WorkflowTextStart):
            return None
        snapshot = request.start.semantic_snapshot
        if snapshot is None:
            return None
        try:
            semantic = AgentSemanticParseResult.model_validate(snapshot)
        except ValidationError as exc:
            raise WorkflowPlanningError(
                "WORKFLOW_SEMANTIC_SNAPSHOT_INVALID",
                "工作流语义快照无效，请重新发起本次操作。",  # noqa: RUF001
            ) from exc

        # Supplements are typed by the interaction that requested them. Only
        # the addressed slot is patched; untouched facts from the original
        # turn remain canonical. Quality supplementation intentionally keeps
        # the legacy full-reparse behavior because it asks the user to revise
        # the whole activity narrative.
        for supplement in request.supplements:
            business_action = supplement.metadata.get("business_action")
            if business_action == "provide_workflow_customer":
                semantic.customer = semantic.customer.model_copy(
                    update={
                        "name_text": supplement.content,
                        "resolution_source": "EXPLICIT",
                    }
                )
            elif business_action == "provide_follow_up_content":
                semantic.follow_up = semantic.follow_up.model_copy(
                    update={"content": supplement.content}
                )
            elif business_action == "supplement_follow_up_next_action":
                semantic.follow_up = semantic.follow_up.model_copy(
                    update={"next_action": supplement.content}
                )
            elif business_action == "supplement_follow_up_quality":
                return None
        return semantic

    @staticmethod
    def _with_resolved_customer(
        request: WorkflowTurnInput,
        *,
        semantic: object,
        customer_id: str,
        customer_name: str,
    ) -> WorkflowTurnInput:
        semantic_customer = getattr(semantic, "customer", None)
        lookup_name = getattr(semantic_customer, "name_text", None)
        if not isinstance(lookup_name, str) or not lookup_name.strip():
            lookup_name = customer_name
        return request.model_copy(
            update={
                "resolved_customer": WorkflowResolvedCustomer(
                    customer_id=customer_id,
                    customer_name=customer_name,
                    lookup_name=lookup_name.strip(),
                )
            }
        )

    async def _validate_cached_customer(
        self,
        cached_customer: object,
        *,
        runtime: WorkflowRuntimeContext,
    ) -> object:
        validator = getattr(self._customer_resolver, "validate_cached", None)
        if callable(validator):
            try:
                return await validator(
                    customer_id=cached_customer.customer_id,
                    authorization=self._authorization(runtime),
                )
            except WorkflowResourceResolutionError as exc:
                raise WorkflowPlanningError(
                    "WORKFLOW_CUSTOMER_RESOLUTION_FAILED",
                    exc.message,
                    retryable=exc.retryable,
                ) from exc
        # Test doubles and alternate resolvers without the optional validation
        # seam can still use the server-issued checkpoint identity without a
        # name search. Production CRMWorkflowCustomerResolver implements the
        # authoritative validation call below.
        from app.services.agent.query.schemas import EntityRef

        return await self._customer_resolver.resolve(
            customer_lookup_name=None,
            trusted_context_customer=EntityRef(
                ref_id=f"eref_customer_{cached_customer.customer_id}",
                resource="customer",
                public_id=cached_customer.customer_id,
                display_name=cached_customer.customer_name,
            ),
            selected_customer_id=None,
            authorization=self._authorization(runtime),
        )

    async def _resolve_customer(
        self,
        semantic: object,
        *,
        request: WorkflowTurnInput,
        workflow_id: str,
        runtime: WorkflowRuntimeContext,
    ) -> tuple[str, str]:
        cached_customer = request.resolved_customer
        # The Root decision has already determined whether this turn
        # continues the active task.  A resolved_customer is therefore a
        # server-bound identity, not a name cache to compare with another
        # piece of free text.  Requiring string equality here caused harmless
        # aliases/abbreviations in later turns to trigger a fresh search.
        # Switching to another customer starts a new task and arrives without
        # this binding; the authoritative validator still runs before any
        # mutation.
        if cached_customer is not None:
            resolution = await self._validate_cached_customer(
                cached_customer,
                runtime=runtime,
            )
            if resolution.status == "RESOLVED" and resolution.customer is not None:
                return resolution.customer.customer_id, resolution.customer.customer_name
            if resolution.status == "NOT_FOUND":
                raise self._needs_text(
                    workflow_id=workflow_id,
                    field="customer_name",
                    business_action="provide_workflow_customer",
                    title="重新确认客户",
                    prompt="没有匹配客户，请提供更完整的客户名称。",  # noqa: RUF001
                    checkpoint_request=request,
                )

        trusted_context_customer = (
            request.selected_entity
            if request.selected_entity is not None and request.selected_entity.resource == "customer"
            else None
        )
        selected_customer_id = self._latest_supplement_metadata_for_action(
            request,
            "customer_id",
            business_action="select_workflow_customer",
        )
        binding = bind_workflow_customer(
            semantic=semantic,
            trusted_context_customer=trusted_context_customer,
            selected_customer_id=selected_customer_id,
        )
        customer_lookup_name = binding.lookup_name
        trusted_context_customer = binding.trusted_context_customer
        selected_customer_id = binding.selected_customer_id
        try:
            resolution = await self._customer_resolver.resolve(
                customer_lookup_name=customer_lookup_name,
                trusted_context_customer=trusted_context_customer,
                selected_customer_id=selected_customer_id,
                authorization=self._authorization(runtime),
            )
        except WorkflowResourceResolutionError as exc:
            raise WorkflowPlanningError(
                "WORKFLOW_CUSTOMER_RESOLUTION_FAILED",
                exc.message,
                retryable=exc.retryable,
            ) from exc

        if resolution.status == "SELECTION_REQUIRED":
            raise WorkflowPlanningNeedsInput(
                self._workflow_customer_choice(
                    workflow_id=workflow_id,
                    candidates=resolution.candidates,
                    stale_selection=selected_customer_id is not None,
                ),
                checkpoint_request=request,
            )
        if resolution.status == "MISSING":
            raise self._needs_text(
                workflow_id=workflow_id,
                field="customer_name",
                business_action="provide_workflow_customer",
                title="补充客户",
                prompt="请说明这项业务操作对应哪个客户。",
                checkpoint_request=request,
            )
        if resolution.status == "NOT_FOUND" or resolution.customer is None:
            customer_label = f"“{customer_lookup_name}”" if customer_lookup_name else "该客户"
            raise self._needs_text(
                workflow_id=workflow_id,
                field="customer_name",
                business_action="provide_workflow_customer",
                title="重新确认客户",
                prompt=f"没有找到可访问的客户{customer_label}, 请提供更完整的客户名称。",
                checkpoint_request=request,
            )
        return resolution.customer.customer_id, resolution.customer.customer_name

    @staticmethod
    def _workflow_customer_choice(
        *,
        workflow_id: str,
        candidates: tuple[WorkflowCustomerCandidate, ...],
        stale_selection: bool,
    ) -> WorkflowInteraction:
        return WorkflowInteraction(
            interaction_id=f"int_{workflow_id.removeprefix('wf_')}_customer",
            interaction_type="choice",
            business_action="select_workflow_customer",
            title="选择客户",
            prompt=(
                "之前选择的客户已失效, 请重新选择。"
                if stale_selection
                else "找到多个匹配客户, 请选择本次业务操作对应的客户。"
            ),
            options=[
                WorkflowInteractionOption(
                    value=candidate.customer_id,
                    label=candidate.customer_name,
                    description=candidate.city,
                    metadata={
                        "customer_id": candidate.customer_id,
                        "customer_name": candidate.customer_name,
                    },
                )
                for candidate in candidates
            ],
            selection_mode="single",
            min_selections=1,
            max_selections=1,
            submit_label="继续",
        )

    @staticmethod
    def _latest_supplement_metadata(
        request: WorkflowTurnInput,
        key: str,
    ) -> str | None:
        for supplement in reversed(request.supplements):
            value = supplement.metadata.get(key)
            if isinstance(value, str) and value:
                return value
        return None

    @staticmethod
    def _latest_supplement_metadata_for_action(
        request: WorkflowTurnInput,
        key: str,
        *,
        business_action: str,
    ) -> str | None:
        for supplement in reversed(request.supplements):
            if supplement.metadata.get("business_action") != business_action:
                continue
            value = supplement.metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if value is not None:
                raise WorkflowPlanningError(
                    "WORKFLOW_SIGNED_SELECTION_INVALID",
                    "工作流选择结果无效,请重新选择。",
                )
        return None

    @staticmethod
    def _latest_supplement_int_metadata(
        request: WorkflowTurnInput,
        key: str,
        *,
        business_action: str,
    ) -> int | None:
        for supplement in reversed(request.supplements):
            if supplement.metadata.get("business_action") != business_action:
                continue
            value = supplement.metadata.get(key)
            if isinstance(value, int) and not isinstance(value, bool) and value > 0:
                return value
            if value is not None:
                raise WorkflowPlanningError(
                    "WORKFLOW_SIGNED_SELECTION_INVALID",
                    "工作流选择结果无效,请重新选择。",
                )
        return None

    @staticmethod
    def _authorization(runtime: WorkflowRuntimeContext) -> str:
        authorization = runtime.authorization
        if not isinstance(authorization, str) or not authorization:
            raise WorkflowPlanningError(
                "WORKFLOW_AUTHORIZATION_REQUIRED",
                "工作流缺少有效授权,无法读取业务资源。",
                retryable=True,
            )
        return authorization

    @staticmethod
    def _optional_non_blank_text(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        normalized = value.strip()
        return normalized or None

    def _current_datetime(self, runtime: WorkflowRuntimeContext) -> datetime:
        value = runtime.metadata.get("current_datetime")
        if isinstance(value, datetime):
            return value
        return self._temporal_resolver.now()

    @staticmethod
    def _planning_text(original_text: str, supplements: list[WorkflowSupplement]) -> str:
        if not supplements:
            return original_text.strip()
        supplement_text = "\n".join(f"补充信息: {item.content}" for item in supplements)
        return f"{original_text.strip()}\n{supplement_text}"
