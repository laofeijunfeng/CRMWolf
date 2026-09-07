"""Project typed Root Orchestrator results into the CRM Agent UI protocol."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, cast

if TYPE_CHECKING:
    from pydantic import JsonValue

    from app.services.agent.orchestrator import WorkflowContinuation
    from app.services.agent.query.registry import CustomerContextResult
    from app.services.agent.query.schemas import CRMQueryResult, EntityRef
    from app.services.agent.workflow import WorkflowInteraction, WorkflowProgress

from app.schemas.agent_persistence import (
    AgentUIActionConsumptionMode,
    AgentUIActionRootContextRole,
    AgentUIActionType,
    AgentUIMessageBody,
)
from app.services.agent.orchestrator import (
    FailureDispatchResult,
    QueryDispatchResult,
    RootDispatchResult,
    WorkflowDispatchResult,
)
from app.services.agent.ui.markdown import (
    normalize_agent_markdown_for_ui,
    project_agent_markdown_to_plain_text,
)
from app.services.agent.ui.schemas import (
    AgentErrorCode,
    AgentUIBlock,
    AgentUIMetadata,
    EntityListBlock,
    EntityListItem,
    ErrorBlock,
    InteractionBlock,
    InteractionField,
    InteractionOption,
    ProcessBlock,
    ProcessItem,
    TextBlock,
)
from app.utils.public_id import generate_public_id

AgentUIRoute = Literal["QUERY", "WORKFLOW", "CLARIFY"]
_UI_ERROR_CODE_BY_INTERNAL_CODE = {
    "ROOT_DECISION_MODEL_TIMEOUT": "UPSTREAM_TIMEOUT",
    "ROOT_DECISION_MODEL_UNAVAILABLE": "UPSTREAM_UNAVAILABLE",
    "ROOT_DECISION_INVALID_OUTPUT": "MODEL_OUTPUT_INVALID",
    "ROOT_CONTEXT_UNAVAILABLE": "CHECKPOINT_UNAVAILABLE",
    "WORKFLOW_CHECKPOINT_UNAVAILABLE": "CHECKPOINT_UNAVAILABLE",
    "INTERACTION_RESOLUTION_UNAVAILABLE": "ACTION_INVALID",
    "QUERY_SEMANTIC_INTENT_UNAVAILABLE": "UPSTREAM_UNAVAILABLE",
    "QUERY_IDENTITY_UNAVAILABLE": "UPSTREAM_UNAVAILABLE",
    "QUERY_EXECUTION_FAILED": "UPSTREAM_UNAVAILABLE",
    "WORKFLOW_EXECUTION_FAILED": "UPSTREAM_UNAVAILABLE",
}

_FAILURE_TITLE_BY_CODE = {
    "ROOT_DECISION_MODEL_TIMEOUT": "这次没处理成",
    "ROOT_DECISION_MODEL_UNAVAILABLE": "这次没处理成",
    "ROOT_DECISION_INVALID_OUTPUT": "还没理解清楚",
    "ROOT_CONTEXT_UNAVAILABLE": "对话没接上",
    "WORKFLOW_CHECKPOINT_UNAVAILABLE": "操作没接上",
    "INTERACTION_RESOLUTION_UNAVAILABLE": "操作没接上",
    "QUERY_SEMANTIC_INTENT_UNAVAILABLE": "查询没完成",
    "QUERY_IDENTITY_UNAVAILABLE": "客户没确认",
    "QUERY_EXECUTION_FAILED": "查询没完成",
    "WORKFLOW_EXECUTION_FAILED": "操作没完成",
    "WORKFLOW_CUSTOMER_NOT_FOUND": "没找到这个客户",
    "WORKFLOW_CRM_API_UNAVAILABLE": "操作没完成",
    "WORKFLOW_CRM_API_REJECTED": "操作没完成",
    # Canonical query errors can arrive after the query executor has already
    # normalized an internal provider/validation failure.  Keep their title
    # user-facing even though the UI code is intentionally generic.
    "QUERY_INVALID": "查询没完成",
    "QUERY_UNSUPPORTED": "查询没完成",
    "QUERY_EMPTY": "查询没完成",
    "QUERY_LIMIT_EXCEEDED": "查询没完成",
    "UPSTREAM_TIMEOUT": "这次没处理成",
    "UPSTREAM_UNAVAILABLE": "这次没处理成",
    "MODEL_OUTPUT_INVALID": "还没理解清楚",
    "INTERNAL_ERROR": "这次没处理成",
}


_ALLOWED_ERROR_CODES = {
    "ROUTE_AMBIGUOUS",
    "ENTITY_AMBIGUOUS",
    "QUERY_INVALID",
    "QUERY_UNSUPPORTED",
    "QUERY_EMPTY",
    "PERMISSION_DENIED",
    "QUERY_LIMIT_EXCEEDED",
    "UPSTREAM_TIMEOUT",
    "UPSTREAM_UNAVAILABLE",
    "CHECKPOINT_UNAVAILABLE",
    "MODEL_OUTPUT_INVALID",
    "RESULT_SET_EXPIRED",
    "ACTION_ALREADY_CONSUMED",
    "ACTION_EXPIRED",
    "ACTION_INVALID",
    "TURN_IN_PROGRESS",
    "IDEMPOTENCY_KEY_REUSED",
    "INTERNAL_ERROR",
}


@dataclass(frozen=True)
class AgentUIActionDraft:
    """Server-signed action data waiting for the final message identity."""

    public_id: str
    action_type: AgentUIActionType
    root_context_role: AgentUIActionRootContextRole
    target: dict[str, JsonValue]
    consumption_mode: AgentUIActionConsumptionMode


@dataclass(frozen=True)
class AgentUIComposition:
    """Pure-text projection, validated UI body, and actions to persist atomically."""

    content: str
    body: AgentUIMessageBody
    action_drafts: tuple[AgentUIActionDraft, ...] = ()


class AgentUIComposer:
    """Project typed Root results without inspecting runtime state or events."""

    def compose_follow_up_task_confirmations(
        self,
        dispatches: list[WorkflowDispatchResult],
        *,
        case_public_ids: list[str],
    ) -> AgentUIComposition:
        """Compose one compact message while preserving one signed action per Workflow."""

        if not dispatches:
            raise ValueError("follow-up task confirmation composition requires at least one dispatch")
        if len(case_public_ids) != len(dispatches) or any(
            not isinstance(case_public_id, str) or not case_public_id
            for case_public_id in case_public_ids
        ):
            raise ValueError("follow-up task confirmation case IDs must match dispatches")

        blocks: list[AgentUIBlock] = []
        actions: list[AgentUIActionDraft] = []
        for index, dispatch in enumerate(dispatches, start=1):
            result = dispatch.workflow_result
            if result.status != "WAITING" or dispatch.continuation is None:
                raise ValueError("follow-up task confirmation dispatch must be waiting with continuation")
            if result.interaction.business_action != "resolve_follow_up_task_confirmation_case":
                raise ValueError("dispatch is not a follow-up task confirmation")
            block, action = self._interaction_block(
                result.interaction,
                continuation=dispatch.continuation,
                follow_up_confirmation_case_public_id=case_public_ids[index - 1],
                root_context_role="PENDING_CASE",
            )
            blocks.append(block.model_copy(update={"id": f"b_task_completion_{index}"}))
            actions.append(action)

        count = len(dispatches)
        content = (
            dispatches[0].workflow_result.assistant_text
            if count == 1
            else f"有 {count} 个待办需要确认完成状态。"
        )
        return self._composition(
            text=content,
            route="WORKFLOW",
            blocks=tuple(blocks),
            actions=tuple(actions),
            include_text_block=False,
        )

    def compose_customer_opportunity_suggestion(
        self,
        *,
        decision: str,
        job_public_id: str,
        action_public_id: str,
    ) -> AgentUIComposition:
        """Project a completed opportunity suggestion into a server-triggered confirmation.

        This interaction deliberately has no native Workflow continuation yet: the
        background suggestion job is not a waiting Workflow. The signed action
        target carries the durable suggestion identity and the Root server trigger
        starts the independent opportunity Workflow only after the user chooses.
        """
        if decision not in {"CREATE_OPPORTUNITY", "MOVE_OPPORTUNITY_STAGE"}:
            raise ValueError("unsupported opportunity suggestion decision")
        if not job_public_id or not action_public_id:
            raise ValueError("opportunity suggestion projection IDs are required")

        is_create = decision == "CREATE_OPPORTUNITY"
        prompt = (
            "我看到有一个比较明确的商机，是否帮你直接创建？"  # noqa: RUF001
            if is_create
            else "我看到这个商机有明确的推进机会，是否帮你推进？"  # noqa: RUF001
        )
        interaction_id = f"int_{job_public_id}_opportunity_suggestion"
        target: dict[str, JsonValue] = {
            "workflow_trigger": {
                "type": "workflow_trigger",
                "workflow": "customer_opportunity_suggestion",
                "job_public_id": job_public_id,
                "action": decision,
            },
            "interaction_id": interaction_id,
            "interaction_type": "confirmation",
            "business_action": "customer_opportunity_suggestion",
            "submit_label": "提交",
            "submit_on_select": True,
            "choices": [
                {"value": "confirm", "label": "是"},
                {"value": "cancel", "label": "否"},
            ],
            "selection_mode": "single",
        }
        block = InteractionBlock(
            id="b_opportunity_suggestion",
            type="interaction",
            interaction_id=interaction_id,
            interaction_type="confirmation",
            state="ACTIVE",
            prompt=prompt,
            fields=[],
            options=[
                InteractionOption(value="confirm", label="是"),
                InteractionOption(value="cancel", label="否"),
            ],
            selection_mode="single",
            allow_blank=None,
            submit_on_select=True,
            submit_label="提交",
            submit_action_id=action_public_id,
        )
        action = AgentUIActionDraft(
            public_id=action_public_id,
            action_type="submit_interaction",
            root_context_role="PROJECTION_ONLY",
            target=target,
            consumption_mode="ONE_SHOT",
        )
        # The interaction block is the sole visual carrier for this actionable
        # suggestion.  Keep ``text`` for persistence, search, accessibility,
        # and non-UI channel fallbacks, but do not render a second TextBlock
        # with the same prompt above the card.
        return self._composition(
            text=prompt,
            route="WORKFLOW",
            blocks=(block,),
            actions=(action,),
            include_text_block=False,
        )

    def compose(self, dispatch: RootDispatchResult) -> AgentUIComposition:
        if isinstance(dispatch, QueryDispatchResult):
            return self._compose_query(dispatch)
        if isinstance(dispatch, WorkflowDispatchResult):
            return self._compose_workflow(dispatch)
        if isinstance(dispatch, FailureDispatchResult):
            return self._error_composition(
                text=dispatch.error.message,
                route=self._route(dispatch),
                block=self._error_block(
                    code=dispatch.error.code,
                    title=self._failure_title(dispatch),
                    message=dispatch.error.message,
                    retryable=dispatch.error.retryable,
                ),
            )
        return self._composition(
            text=dispatch.clarification.question,
            route="CLARIFY",
        )

    def _compose_query(self, dispatch: QueryDispatchResult) -> AgentUIComposition:
        response = dispatch.query_result.response
        text = response.answer or response.clarification_question
        if text is None:
            raise ValueError("Query result has no user-visible response")

        query_projection = self._query_block(dispatch.query_result.query_results)
        context_projection = None
        if query_projection is None:
            context_projection = self._authoritative_entity_block(
                dispatch.query_result.authoritative_entity_refs
            )
        if context_projection is None and query_projection is None:
            context_projection = self._customer_context_block(
                dispatch.query_result.customer_context_results
            )
        block = query_projection or context_projection
        if block is None:
            return self._composition(text=text, route="QUERY")
        if query_projection is not None and block.entity_type == "customer":
            text = f"共找到 {block.total} 家公司。"
        return self._composition(
            text=text,
            route="QUERY",
            blocks=(block,),
            result_set_id=block.result_set_id,
        )

    def _compose_workflow(self, dispatch: WorkflowDispatchResult) -> AgentUIComposition:
        result = dispatch.workflow_result
        if result.status == "REPLAY":
            raise ValueError("Workflow replay must be projected from its persisted message")
        process_block = self.process_block(result.progress)
        if result.status == "FAILED":
            return self._error_composition(
                text=result.message,
                route="WORKFLOW",
                block=self._error_block(
                    code=result.code,
                    title=_FAILURE_TITLE_BY_CODE.get(result.code, "操作没完成"),
                    message=result.message,
                    retryable=result.retryable,
                ),
                blocks=(process_block,),
            )
        if result.status == "SKIPPED":
            return self._composition(
                text="",
                route="WORKFLOW",
                leading_blocks=(process_block,),
                include_text_block=False,
            )
        if result.status != "WAITING":
            return self._composition(
                text=result.assistant_text,
                route="WORKFLOW",
                leading_blocks=(process_block,),
            )
        if dispatch.continuation is None:
            raise ValueError("Waiting Workflow result has no continuation")
        interaction_block, action = self._interaction_block(
            result.interaction,
            continuation=dispatch.continuation,
            root_context_role=(
                "PENDING_CASE"
                if result.interaction.business_action == "resolve_follow_up_task_confirmation_case"
                else "RESUMABLE_WORKFLOW"
            ),
        )
        compact_task_completion = (
            result.interaction.business_action == "resolve_follow_up_task_confirmation_case"
        )
        return self._composition(
            text=result.assistant_text,
            route="WORKFLOW",
            leading_blocks=() if compact_task_completion else (process_block,),
            blocks=(interaction_block,),
            actions=(action,),
            include_text_block=False,
        )

    @staticmethod
    def _route(dispatch: FailureDispatchResult) -> AgentUIRoute | None:
        if dispatch.decision is None:
            return None
        return dispatch.decision.route

    @classmethod
    def _failure_title(cls, dispatch: FailureDispatchResult) -> str:
        # Query execution reuses canonical transport/model error codes that
        # are also valid for Root.  The route is the only reliable way to
        # keep the title truthful without exposing internal exception names.
        if (
            dispatch.decision is not None
            and dispatch.decision.route == "QUERY"
            and dispatch.error.code in {
                "QUERY_INVALID",
                "QUERY_UNSUPPORTED",
                "QUERY_EMPTY",
                "QUERY_LIMIT_EXCEEDED",
                "QUERY_SEMANTIC_INTENT_UNAVAILABLE",
                "QUERY_IDENTITY_UNAVAILABLE",
                "QUERY_EXECUTION_FAILED",
                "UPSTREAM_TIMEOUT",
                "UPSTREAM_UNAVAILABLE",
                "MODEL_OUTPUT_INVALID",
            }
        ):
            return "查询没完成"
        return _FAILURE_TITLE_BY_CODE.get(dispatch.error.code, "这次没处理成")

    @staticmethod
    def _error_composition(
        *,
        text: str,
        route: AgentUIRoute | None,
        block: ErrorBlock,
        blocks: tuple[AgentUIBlock, ...] = (),
    ) -> AgentUIComposition:
        projected_content = project_agent_markdown_to_plain_text(text)
        return AgentUIComposition(
            content=projected_content,
            body=AgentUIMessageBody(
                state="final",
                blocks=[*blocks, block],
                suggested_actions=[],
                metadata=AgentUIMetadata(
                    route=route,
                    accessibility_label=projected_content,
                ),
            ),
        )

    @staticmethod
    def _composition(
        *,
        text: str,
        route: AgentUIRoute | None,
        leading_blocks: tuple[AgentUIBlock, ...] = (),
        blocks: tuple[AgentUIBlock, ...] = (),
        actions: tuple[AgentUIActionDraft, ...] = (),
        result_set_id: str | None = None,
        include_text_block: bool = True,
    ) -> AgentUIComposition:
        projected_content = project_agent_markdown_to_plain_text(text)
        safe_text, text_format = normalize_agent_markdown_for_ui(text)
        text_blocks: tuple[AgentUIBlock, ...] = ()
        if include_text_block:
            text_blocks = (
                TextBlock(
                    id="b_text_1",
                    type="text",
                    format=text_format,
                    text=safe_text,
                ),
            )
        return AgentUIComposition(
            content=projected_content,
            body=AgentUIMessageBody(
                state="final",
                blocks=[*leading_blocks, *text_blocks, *blocks],
                suggested_actions=[],
                metadata=AgentUIMetadata(
                    route=route,
                    result_set_id=result_set_id,
                    accessibility_label=projected_content,
                ),
            ),
            action_drafts=actions,
        )

    @staticmethod
    def process_block(progress: WorkflowProgress) -> ProcessBlock:
        """Project one channel-neutral Workflow progress snapshot into Agent UI."""
        return ProcessBlock(
            id="b_process_1",
            type="process",
            title="执行过程",
            items=[
                ProcessItem(
                    key=step.key,
                    title=step.title,
                    status=step.status,
                    description=step.description,
                )
                for step in progress.steps
            ],
        )

    def _query_block(
        self,
        query_results: list[CRMQueryResult],
    ) -> EntityListBlock | None:
        result = next((item for item in query_results if item.rows or item.status == "EMPTY"), None)
        if result is None:
            return None

        if not result.entity_refs:
            return None
        if len(result.entity_refs) != len(result.rows):
            raise ValueError("Query entity list rows require authoritative entity references")

        items = [EntityListItem(entity_ref=ref) for ref in result.entity_refs]
        return EntityListBlock(
            id="b_entity_list_1",
            type="entity_list",
            entity_type=result.resource,
            items=items,
            total=result.total if result.total is not None else len(items),
            result_set_id=result.result_set_id,
        )

    @staticmethod
    def _authoritative_entity_block(
        refs: list[EntityRef],
    ) -> EntityListBlock | None:
        if not refs:
            return None
        resources = {ref.resource for ref in refs}
        if len(resources) != 1:
            return None
        unique_refs = []
        seen: set[tuple[str, str]] = set()
        for ref in refs:
            key = (ref.resource, ref.public_id)
            if key not in seen:
                seen.add(key)
                unique_refs.append(ref)
        result_set_id = unique_refs[0].result_set_id
        if any(ref.result_set_id != result_set_id for ref in unique_refs):
            result_set_id = None
            unique_refs = [
                ref.model_copy(update={"result_set_id": None}) for ref in unique_refs
            ]
        return EntityListBlock(
            id="b_entity_list_1",
            type="entity_list",
            entity_type=unique_refs[0].resource,
            items=[EntityListItem(entity_ref=ref) for ref in unique_refs],
            total=len(unique_refs),
            result_set_id=result_set_id,
        )

    @classmethod
    def _customer_context_block(
        cls,
        context_results: list[CustomerContextResult],
    ) -> EntityListBlock | None:
        """Expose customer-context targets as clickable entity references."""

        return cls._authoritative_entity_block(
            [result.customer_ref for result in context_results]
        )

    def _interaction_block(
        self,
        interaction: WorkflowInteraction,
        *,
        continuation: WorkflowContinuation,
        follow_up_confirmation_case_public_id: str | None = None,
        root_context_role: AgentUIActionRootContextRole,
    ) -> tuple[InteractionBlock, AgentUIActionDraft]:
        public_id = generate_public_id("act")
        compact_task_completion = (
            interaction.business_action == "resolve_follow_up_task_confirmation_case"
        )
        ui_source_options = interaction.options
        if compact_task_completion:
            completion_option = next(
                (option for option in interaction.options if option.value == "已完成"),
                None,
            )
            if completion_option is None:
                raise ValueError("Follow-up task confirmation requires a completion choice")
            ui_source_options = [completion_option]
        options = [
            InteractionOption(
                value=option.value,
                label=option.label,
                description=option.description,
                disabled=option.disabled,
            )
            for option in ui_source_options
        ]
        fields = [
            InteractionField(
                key=field.key,
                label=field.label,
                field_type=field.field_type,
                required=field.required,
                placeholder=field.placeholder,
                default_value=field.default_value,
                min_length=field.min_length,
                max_length=field.max_length,
                minimum=field.minimum,
                maximum=field.maximum,
                options=[
                    InteractionOption(
                        value=option.value,
                        label=option.label,
                        description=option.description,
                        disabled=option.disabled,
                    )
                    for option in field.options
                ],
            )
            for field in interaction.fields
        ]
        if interaction.interaction_type == "text_input":
            allow_blank = interaction.allow_blank is True
            fields = [
                InteractionField(
                    key="text",
                    label=interaction.title,
                    field_type="textarea",
                    required=not allow_blank,
                    min_length=0 if allow_blank else 1,
                    max_length=10_000,
                )
            ]

        target: dict[str, JsonValue] = {
            "workflow_continuation": continuation.model_dump(mode="json"),
            "interaction_id": interaction.interaction_id,
            "interaction_type": interaction.interaction_type,
            "business_action": interaction.business_action,
            "submit_label": interaction.submit_label,
            "submit_on_select": interaction.submit_on_select,
        }
        if follow_up_confirmation_case_public_id is not None:
            target["follow_up_confirmation_case_public_id"] = follow_up_confirmation_case_public_id
        if compact_task_completion:
            target["result_display"] = "STATE_UPDATE"
        if options:
            signed_choices: list[dict[str, JsonValue]] = []
            for option in ui_source_options:
                signed_choice = option.model_dump(mode="json")
                if not option.metadata:
                    signed_choice.pop("metadata", None)
                signed_choices.append(signed_choice)
            target["choices"] = signed_choices
        if fields:
            target["fields"] = [field.model_dump(mode="json") for field in fields]
        if interaction.selection_mode is not None:
            target["selection_mode"] = interaction.selection_mode
        if interaction.interaction_type == "choice":
            target["min_selections"] = interaction.min_selections
            target["max_selections"] = interaction.max_selections
        if interaction.allow_blank is not None:
            target["allow_blank"] = interaction.allow_blank

        ui_min_selections = interaction.min_selections if interaction.interaction_type == "choice" else None
        ui_max_selections = interaction.max_selections if interaction.interaction_type == "choice" else None
        return (
            InteractionBlock(
                id="b_interaction_1",
                type="interaction",
                interaction_id=interaction.interaction_id,
                interaction_type=interaction.interaction_type,
                presentation="COMPACT_TASK_COMPLETION" if compact_task_completion else None,
                state="ACTIVE",
                prompt=interaction.prompt,
                fields=fields,
                options=options,
                selection_mode=interaction.selection_mode,
                min_selections=ui_min_selections,
                max_selections=ui_max_selections,
                allow_blank=interaction.allow_blank,
                submit_on_select=interaction.submit_on_select,
                submit_label=interaction.submit_label,
                submit_action_id=public_id,
            ),
            AgentUIActionDraft(
                public_id=public_id,
                action_type="submit_interaction",
                root_context_role=root_context_role,
                target=target,
                consumption_mode="ONE_SHOT",
            ),
        )

    @staticmethod
    def _error_block(
        *,
        code: str,
        title: str,
        message: str,
        retryable: bool,
    ) -> ErrorBlock:
        normalized_code = _UI_ERROR_CODE_BY_INTERNAL_CODE.get(code, code)
        normalized = cast(
            "AgentErrorCode",
            normalized_code if normalized_code in _ALLOWED_ERROR_CODES else "INTERNAL_ERROR",
        )
        return ErrorBlock(
            id="b_error_1",
            type="error",
            code=normalized,
            title=title,
            message=message,
            retryable=retryable,
        )
