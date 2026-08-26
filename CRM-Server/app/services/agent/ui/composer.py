"""Project typed Root Orchestrator results into the CRM Agent UI protocol."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, cast

if TYPE_CHECKING:
    from pydantic import JsonValue

    from app.services.agent.orchestrator import WorkflowContinuation
    from app.services.agent.query.schemas import CRMQueryResult
    from app.services.agent.workflow import WorkflowInteraction, WorkflowProgress

from app.schemas.agent_persistence import AgentUIActionConsumptionMode, AgentUIActionType, AgentUIMessageBody
from app.services.agent.orchestrator import (
    FailureDispatchResult,
    QueryDispatchResult,
    RootDispatchResult,
    WorkflowDispatchResult,
)
from app.services.agent.ui.markdown import project_agent_markdown_to_plain_text
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
_ALLOWED_ERROR_CODES = {
    "ROUTE_AMBIGUOUS",
    "ENTITY_AMBIGUOUS",
    "QUERY_INVALID",
    "QUERY_UNSUPPORTED",
    "QUERY_EMPTY",
    "PERMISSION_DENIED",
    "QUERY_LIMIT_EXCEEDED",
    "UPSTREAM_TIMEOUT",
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
                    title="处理未完成",
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
        if query_projection is None:
            return self._composition(text=text, route="QUERY")
        block = query_projection
        if block.entity_type == "customer":
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
                    title="操作未完成",
                    message=result.message,
                    retryable=result.retryable,
                ),
                blocks=(process_block,),
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
        text_blocks: tuple[AgentUIBlock, ...] = ()
        if include_text_block:
            text_blocks = (
                TextBlock(
                    id="b_text_1",
                    type="text",
                    format="markdown",
                    text=text,
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

    def _interaction_block(
        self,
        interaction: WorkflowInteraction,
        *,
        continuation: WorkflowContinuation,
        follow_up_confirmation_case_public_id: str | None = None,
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
        normalized = cast("AgentErrorCode", code if code in _ALLOWED_ERROR_CODES else "INTERNAL_ERROR")
        return ErrorBlock(
            id="b_error_1",
            type="error",
            code=normalized,
            title=title,
            message=message,
            retryable=retryable,
        )
