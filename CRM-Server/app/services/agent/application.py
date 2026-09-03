"""Channel-independent application boundary for CRM Agent turns."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from time import monotonic
from typing import TYPE_CHECKING

from fastapi import HTTPException
from pydantic import JsonValue, ValidationError

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.crud.agent import agent_session_crud
from app.crud.ai_config import ai_config_crud
from app.crud.permission import permission_crud
from app.models.agent import AgentMessage, AgentMessageRole
from app.models.agent_persistence import AgentUIActionStatus
from app.schemas.agent import (
    AgentSessionCreate,
    AgentSSEAgentUIDeltaEvent,
    AgentSSEAgentUIFinalEvent,
    AgentSSEDoneEvent,
    AgentSSEEventEnvelope,
    AgentSSESessionEvent,
    AgentSSETransportErrorEvent,
)
from app.schemas.agent_persistence import (
    AgentAssistantMessageCreate,
    AgentQueryResultSetCreate,
    AgentResultPage,
    AgentTurnStart,
    AgentUIActionRegistration,
    AgentUIMessageBody,
)
from app.services.agent import agent_copy
from app.services.agent.durable_work import AgentDurableWorkBinder, agent_durable_work_binder
from app.services.agent.durable_work_contracts import AgentAsyncOperationBinding
from app.services.agent.langchain_runtime import agent_model_enable_thinking
from app.services.agent.orchestrator import (
    AgentExecutionError,
    FailureDispatchResult,
    InteractionTurnInput,
    QueryDispatchResult,
    RootDecisionModelConfig,
    RootDispatchResult,
    RootOrchestrator,
    RootRuntimeContext,
    RootTurnInput,
    TextTurnInput,
    WorkflowDispatchResult,
)
from app.services.agent.orchestrator.runtime import get_root_orchestrator
from app.services.agent.query import CRMQueryAgentModelConfig, CRMQueryAgentResult, EntityRef
from app.services.agent.query.result_sets import AgentQueryResultSetRepository
from app.services.agent.sessions import new_session_key, require_owned_session
from app.services.agent.turns import AgentTurnIdempotencyConflictError, AgentTurnRepository
from app.services.agent.ui.actions import (
    ActionAlreadyConsumedError,
    ActionExpiredError,
    ActionNotFoundError,
    ActionOwnershipError,
    ActionUnavailableError,
    AgentUIActionRepository,
)
from app.services.agent.ui.composer import AgentUIComposer, AgentUIComposition
from app.services.agent.ui.entity_actions import (
    AgentEntityActionResolver,
    EntityActionInvalidError,
    EntityActionPermissionDeniedError,
    EntityActionResolutionError,
    EntityActionResultSetExpiredError,
)
from app.services.agent.ui.input_resolver import AgentUIInputResolutionError
from app.services.agent.ui.schemas import (
    AgentChatInput,
    AgentErrorCode,
    AgentUIEnvelope,
    AgentUIMessageDisplay,
    AgentUIMetadata,
    EntityActionInput,
    InteractionSubmissionInput,
    TextAgentInput,
    TextBlock,
    UpsertBlockOperation,
)
from app.utils.public_id import generate_public_id

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable
    from uuid import UUID

    from sqlalchemy.orm import Session

    from app.services.agent.input import AgentChannelContext
    from app.services.agent.workflow import WorkflowProgress


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _InteractionSubmissionPresentation:
    content: str
    message_display: AgentUIMessageDisplay


@dataclass(frozen=True)
class _PreparedTurnInput:
    content: str
    root_input: TextTurnInput | InteractionTurnInput
    message_display: AgentUIMessageDisplay = "MESSAGE"
    selected_entity_ref: EntityRef | None = None
    entity_action_claim_id: str | None = None
    replay_message_id: int | None = None


class AgentApplicationService:
    """Persist one turn around the single Root Orchestrator dispatch seam."""

    def __init__(
        self,
        *,
        root_orchestrator: RootOrchestrator | None = None,
        session_factory: Callable[[], Session] | None = None,
        turn_repository: AgentTurnRepository | None = None,
        result_set_repository: AgentQueryResultSetRepository | None = None,
        action_repository: AgentUIActionRepository | None = None,
        entity_action_resolver: AgentEntityActionResolver | None = None,
        ui_composer: AgentUIComposer | None = None,
        durable_work_binder: AgentDurableWorkBinder | None = None,
    ) -> None:
        self.root_orchestrator = root_orchestrator or get_root_orchestrator()
        self.session_factory = session_factory or SessionLocal
        self.turn_repository = turn_repository or AgentTurnRepository()
        self.result_set_repository = result_set_repository or AgentQueryResultSetRepository()
        self.action_repository = action_repository or AgentUIActionRepository()
        self.entity_action_resolver = entity_action_resolver or AgentEntityActionResolver(
            result_set_repository=self.result_set_repository
        )
        self.ui_composer = ui_composer or AgentUIComposer()
        self.durable_work_binder = durable_work_binder or agent_durable_work_binder

    async def stream_chat_events(
        self,
        *,
        request_input: AgentChatInput,
        client_request_id: UUID,
        channel_context: AgentChannelContext | None = None,
        team_id: int,
        user_id: int,
        authorization: str,
        session_id: int | None = None,
        session_key: str | None = None,
    ) -> AsyncGenerator[AgentSSEEventEnvelope, None]:
        """Run one typed turn and expose only its authoritative Agent UI result."""

        db = self.session_factory()
        session = None
        turn_start: AgentTurnStart | None = None
        prepared: _PreparedTurnInput | None = None
        dispatch_task: asyncio.Task[RootDispatchResult] | None = None
        input_fingerprint = self._request_input_fingerprint(request_input)
        try:
            if session_id or session_key:
                session = require_owned_session(
                    db,
                    team_id=team_id,
                    user_id=user_id,
                    session_id=session_id,
                    session_key=session_key,
                )
            else:
                title = request_input.text if isinstance(request_input, TextAgentInput) else "Agent 会话"
                session = agent_session_crud.create(
                    db,
                    AgentSessionCreate(
                        session_key=new_session_key(),
                        team_id=team_id,
                        user_id=user_id,
                        title=title[:50],
                    ),
                )

            effective_session_id = int(session.id)
            yield self._session_event(
                session_id=effective_session_id,
                session_key=str(session.session_key),
            )

            permission_codes = frozenset(
                permission.code
                for permission in permission_crud.get_user_permissions(
                    db,
                    user_id=user_id,
                    team_id=team_id,
                )
                if isinstance(getattr(permission, "code", None), str) and permission.code
            )
            prepared = self._prepare_turn_input(
                db,
                request_input=request_input,
                team_id=team_id,
                user_id=user_id,
                session_id=effective_session_id,
                client_request_id=client_request_id,
                permission_codes=permission_codes,
            )
            turn_start = AgentTurnStart(
                team_id=team_id,
                user_id=user_id,
                session_id=effective_session_id,
                client_request_id=client_request_id,
                input_fingerprint=input_fingerprint,
                content=prepared.content,
                ui=self._user_message_body(
                    prepared.content,
                    display=prepared.message_display,
                ),
            )
            begin_result = self.turn_repository.begin(db, turn_start)
            if begin_result.outcome == "COMPLETED":
                db.rollback()
                if begin_result.assistant_message is None:
                    raise RuntimeError("completed turn is missing assistant message")
                yield self._final_stream_event(begin_result.assistant_message.ui)
                yield self._done_event(session_id=effective_session_id)
                return
            if begin_result.outcome == "IN_PROGRESS":
                db.rollback()
                yield self._transport_error(
                    code="TURN_IN_PROGRESS",
                    message="该请求仍在处理中,请稍后通过会话历史重试。",
                    retryable=True,
                    session_id=effective_session_id,
                )
                yield self._done_event(session_id=effective_session_id)
                return
            if prepared.replay_message_id is not None:
                replay_message = self._owned_assistant_message(
                    db,
                    message_id=prepared.replay_message_id,
                    team_id=team_id,
                    user_id=user_id,
                    session_id=effective_session_id,
                )
                db.rollback()
                yield self._final_stream_event(self._message_ui(replay_message))
                yield self._done_event(session_id=effective_session_id)
                return

            # Intake is a short durable transaction. Root/Workflow execution must
            # never keep the user-message insert or an entity-action claim open
            # across model calls and external CRM writes.
            db.commit()

            root_model_config, query_model_config = _load_agent_model_configs(db, team_id=team_id)
            root_turn = RootTurnInput(
                team_id=team_id,
                user_id=user_id,
                session_id=effective_session_id,
                client_request_id=str(client_request_id),
                input=prepared.root_input,
                selected_entity_ref=prepared.selected_entity_ref,
            )
            runtime_context = RootRuntimeContext(
                db=db,
                authorization=authorization,
                permission_codes=permission_codes,
                root_model_config=root_model_config,
                query_model_config=query_model_config,
                metadata=self._runtime_metadata(channel_context),
                deadline_at=monotonic() + get_settings().AGENT_TIMEOUT,
            )
            progress_queue: asyncio.Queue[WorkflowProgress] = asyncio.Queue()
            dispatch_task = asyncio.create_task(
                self.root_orchestrator.dispatch(
                    root_turn,
                    runtime=runtime_context,
                    on_progress=progress_queue.put_nowait,
                )
            )
            stream_sequence = 0
            last_progress: WorkflowProgress | None = None
            while not dispatch_task.done() or not progress_queue.empty():
                if progress_queue.empty():
                    progress_task = asyncio.create_task(progress_queue.get())
                    done, _ = await asyncio.wait(
                        {dispatch_task, progress_task},
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if progress_task not in done:
                        progress_task.cancel()
                        await asyncio.gather(progress_task, return_exceptions=True)
                        continue
                    progress = progress_task.result()
                else:
                    progress = progress_queue.get_nowait()
                if last_progress is not None and progress == last_progress:
                    continue
                last_progress = progress
                stream_sequence += 1
                yield self._progress_stream_event(
                    progress,
                    turn_id=begin_result.user_message.turn_id,
                    sequence=stream_sequence,
                )
            dispatch = await dispatch_task
            replay_message_id = self._workflow_replay_message_id(dispatch)
            if replay_message_id is not None:
                replay_message = self._owned_assistant_message(
                    db,
                    message_id=replay_message_id,
                    team_id=team_id,
                    user_id=user_id,
                    session_id=effective_session_id,
                )
                db.rollback()
                yield self._final_stream_event(
                    self._message_ui(replay_message),
                    sequence=stream_sequence + 1,
                )
                yield self._done_event(session_id=effective_session_id)
                return

            if isinstance(dispatch, QueryDispatchResult):
                dispatch = self._sign_query_result_sets(dispatch)
            composition = self.ui_composer.compose(dispatch)
            if prepared.message_display == "STATE_UPDATE":
                composition = self._with_message_display(
                    composition,
                    display="STATE_UPDATE",
                )
            diagnostics = self._dispatch_diagnostics(dispatch)
            with db.begin_nested():
                completed = self.turn_repository.complete(
                    db,
                    AgentAssistantMessageCreate(
                        team_id=team_id,
                        user_id=user_id,
                        session_id=effective_session_id,
                        turn_id=begin_result.user_message.turn_id,
                        content=composition.content,
                        ui=composition.body,
                        diagnostics=diagnostics,
                    ),
                )
                if isinstance(dispatch, QueryDispatchResult):
                    self._persist_query_result_sets(
                        db,
                        query_result=dispatch.query_result,
                        team_id=team_id,
                        user_id=user_id,
                        session_id=effective_session_id,
                        source_message_id=completed.message.id,
                    )
                for draft in composition.action_drafts:
                    self.action_repository.register(
                        db,
                        AgentUIActionRegistration(
                            public_id=draft.public_id,
                            team_id=team_id,
                            user_id=user_id,
                            session_id=effective_session_id,
                            message_id=completed.message.id,
                            action_type=draft.action_type,
                            root_context_role=draft.root_context_role,
                            target=draft.target,
                            consumption_mode=draft.consumption_mode,
                        ),
                    )
                self._settle_action_claim(
                    db,
                    prepared=prepared,
                    dispatch=dispatch,
                    team_id=team_id,
                    user_id=user_id,
                    session_id=effective_session_id,
                    client_request_id=client_request_id,
                    result_message_id=completed.message.id,
                )
            db.commit()

            self._late_bind_durable_work(
                dispatch,
                team_id=team_id,
                user_id=user_id,
                session_id=effective_session_id,
                source_user_message_id=begin_result.user_message.id,
                source_assistant_message_id=completed.message.id,
            )

            yield self._final_stream_event(
                completed.message.ui,
                sequence=stream_sequence + 1,
            )
            yield self._done_event(session_id=effective_session_id)
        except AgentTurnIdempotencyConflictError:
            db.rollback()
            if session is not None:
                yield self._transport_error(
                    code="IDEMPOTENCY_KEY_REUSED",
                    message="client_request_id 已用于不同输入。",
                    retryable=False,
                    session_id=int(session.id),
                )
                yield self._done_event(session_id=int(session.id))
        except (
            ActionAlreadyConsumedError,
            ActionExpiredError,
            ActionUnavailableError,
            ActionNotFoundError,
            ActionOwnershipError,
            AgentUIInputResolutionError,
            EntityActionResolutionError,
        ) as exc:
            db.rollback()
            if session is None:
                return
            code, message = self._action_error(exc)
            envelope = self._persist_action_error_turn(
                db,
                request_input=request_input,
                client_request_id=client_request_id,
                input_fingerprint=input_fingerprint,
                team_id=team_id,
                user_id=user_id,
                session_id=int(session.id),
                code=code,
                message=message,
            )
            yield self._final_stream_event(envelope)
            yield self._done_event(session_id=int(session.id))
        except HTTPException as exc:
            db.rollback()
            current_session_id = int(session.id) if session is not None else None
            yield self._transport_error(
                code="INTERNAL_ERROR",
                message=str(exc.detail),
                retryable=exc.status_code >= 500,
                session_id=current_session_id,
                status_code=exc.status_code,
            )
            if current_session_id is not None:
                yield self._done_event(session_id=current_session_id)
        except (asyncio.CancelledError, GeneratorExit):
            db.rollback()
            self._persist_interrupted_turn(
                db,
                turn_start=turn_start,
                prepared=prepared,
                team_id=team_id,
                user_id=user_id,
                session_id=int(session.id) if session is not None else None,
                client_request_id=client_request_id,
            )
            raise
        except Exception as exc:
            db.rollback()
            logger.exception("Agent turn failed")
            current_session_id = int(session.id) if session is not None else None
            if current_session_id is not None and turn_start is not None:
                try:
                    begin_result = self.turn_repository.begin(db, turn_start)
                    if begin_result.outcome in {"CREATED", "IN_PROGRESS"}:
                        composition = self.ui_composer.compose(
                            FailureDispatchResult(
                                error=AgentExecutionError(
                                    code="INTERNAL_ERROR",
                                    message=agent_copy.service_error(str(exc)),
                                    retryable=True,
                                )
                            )
                        )
                        if prepared is not None and prepared.message_display == "STATE_UPDATE":
                            composition = self._with_message_display(
                                composition,
                                display="STATE_UPDATE",
                            )
                        completed = self.turn_repository.complete(
                            db,
                            AgentAssistantMessageCreate(
                                team_id=team_id,
                                user_id=user_id,
                                session_id=current_session_id,
                                turn_id=begin_result.user_message.turn_id,
                                content=composition.content,
                                ui=composition.body,
                                diagnostics={"dispatch_type": "failure"},
                            ),
                        )
                        self._release_prepared_action_claim(
                            db,
                            prepared=prepared,
                            team_id=team_id,
                            user_id=user_id,
                            session_id=current_session_id,
                            client_request_id=client_request_id,
                        )
                        db.commit()
                        yield self._final_stream_event(completed.message.ui)
                        yield self._done_event(session_id=current_session_id)
                        return
                except Exception:
                    db.rollback()
                    logger.exception("Agent UI error message persistence failed")
            yield self._transport_error(
                code="INTERNAL_ERROR",
                message="Agent 服务暂时不可用。",
                retryable=True,
                session_id=current_session_id,
            )
            if current_session_id is not None:
                yield self._done_event(session_id=current_session_id)
        finally:
            if dispatch_task is not None and not dispatch_task.done():
                dispatch_task.cancel()
                await asyncio.gather(dispatch_task, return_exceptions=True)
            db.close()

    def _prepare_turn_input(
        self,
        db: Session,
        *,
        request_input: AgentChatInput,
        team_id: int,
        user_id: int,
        session_id: int,
        client_request_id: UUID,
        permission_codes: frozenset[str],
    ) -> _PreparedTurnInput:
        if isinstance(request_input, TextAgentInput):
            return _PreparedTurnInput(
                content=request_input.text,
                root_input=TextTurnInput(type="text", text=request_input.text),
            )
        if isinstance(request_input, InteractionSubmissionInput):
            presentation = self._interaction_submission_presentation(
                db,
                request_input=request_input,
                team_id=team_id,
                user_id=user_id,
                session_id=session_id,
            )
            return _PreparedTurnInput(
                content=presentation.content,
                root_input=InteractionTurnInput(
                    type="interaction",
                    action_id=request_input.action_id,
                    values=request_input.values,
                ),
                message_display=presentation.message_display,
            )
        if not isinstance(request_input, EntityActionInput):
            raise TypeError("unsupported Agent input")

        consumption = self.action_repository.begin_consumption(
            db,
            public_id=request_input.action_id,
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
            client_request_id=client_request_id,
        )
        action = consumption.action
        if action.action_type != "start_workflow":
            raise AgentUIInputResolutionError("entity action does not start a Workflow")
        if consumption.outcome == "REPLAY":
            replay_text = self.entity_action_resolver.replay_start_workflow(action)
            return _PreparedTurnInput(
                content=replay_text,
                root_input=TextTurnInput(type="text", text=replay_text),
                replay_message_id=action.result_message_id,
            )
        resolved = self.entity_action_resolver.resolve_start_workflow(
            db,
            action=action,
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
            permission_codes=permission_codes,
        )
        return _PreparedTurnInput(
            content=resolved.text,
            root_input=TextTurnInput(type="text", text=resolved.text),
            selected_entity_ref=resolved.selected_entity_ref,
            entity_action_claim_id=action.public_id,
        )

    def _interaction_submission_presentation(
        self,
        db: Session,
        *,
        request_input: InteractionSubmissionInput,
        team_id: int,
        user_id: int,
        session_id: int,
    ) -> _InteractionSubmissionPresentation:
        action = self.action_repository.get_owned(
            db,
            public_id=request_input.action_id,
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
        )
        if action is None or action.action_type != "submit_interaction":
            return _InteractionSubmissionPresentation(
                content="已提交",
                message_display="MESSAGE",
            )

        target = action.target
        message_display: AgentUIMessageDisplay = (
            "STATE_UPDATE"
            if target.get("result_display") == "STATE_UPDATE"
            else "MESSAGE"
        )
        interaction_type = target.get("interaction_type")
        submit_on_select = target.get("submit_on_select") is True
        if interaction_type == "confirmation" or (
            interaction_type == "choice" and submit_on_select
        ):
            choice_label = self._submitted_choice_label(
                choices=target.get("choices"),
                submitted_choice=request_input.values.get("choice"),
            )
            if choice_label is not None:
                return _InteractionSubmissionPresentation(
                    content=choice_label,
                    message_display=message_display,
                )

        submit_label = target.get("submit_label")
        return _InteractionSubmissionPresentation(
            content=(
                submit_label.strip()
                if isinstance(submit_label, str) and submit_label.strip()
                else "已提交"
            ),
            message_display=message_display,
        )

    @staticmethod
    def _submitted_choice_label(
        *,
        choices: object,
        submitted_choice: object,
    ) -> str | None:
        if not isinstance(choices, list) or not isinstance(submitted_choice, str):
            return None
        for choice in choices:
            if not isinstance(choice, dict) or choice.get("value") != submitted_choice:
                continue
            label = choice.get("label")
            if isinstance(label, str) and label.strip():
                return label.strip()
        return None

    @staticmethod
    def _with_message_display(
        composition: AgentUIComposition,
        *,
        display: AgentUIMessageDisplay,
    ) -> AgentUIComposition:
        metadata = composition.body.metadata.model_copy(update={"display": display})
        return AgentUIComposition(
            content=composition.content,
            body=composition.body.model_copy(update={"metadata": metadata}),
            action_drafts=composition.action_drafts,
        )

    @staticmethod
    def _sign_query_result_sets(dispatch: QueryDispatchResult) -> QueryDispatchResult:
        signed_results = []
        for result in dispatch.query_result.query_results:
            if result.executed_query is None:
                raise RuntimeError(
                    "completed CRM query result requires an executed query"
                )
            result_set_id = result.result_set_id or generate_public_id("rs")
            signed_results.append(
                result.model_copy(
                    update={
                        "result_set_id": result_set_id,
                        "entity_refs": [
                            ref.model_copy(update={"result_set_id": result_set_id})
                            for ref in result.entity_refs
                        ],
                    }
                )
            )
        return dispatch.model_copy(
            update={
                "query_result": dispatch.query_result.model_copy(
                    update={"query_results": signed_results}
                )
            }
        )

    def _persist_query_result_sets(
        self,
        db: Session,
        *,
        query_result: CRMQueryAgentResult,
        team_id: int,
        user_id: int,
        session_id: int,
        source_message_id: int,
    ) -> None:
        for result in query_result.query_results:
            if result.result_set_id is None or result.executed_query is None:
                raise RuntimeError(
                    "completed CRM query result requires a server-issued result set and executed query"
                )
            ref_count = len(result.entity_refs)
            self.result_set_repository.create(
                db,
                AgentQueryResultSetCreate(
                    public_id=result.result_set_id,
                    team_id=team_id,
                    user_id=user_id,
                    session_id=session_id,
                    source_message_id=source_message_id,
                    resource=result.resource,
                    query=result.executed_query,
                    ordered_entity_refs=result.entity_refs,
                    page=AgentResultPage(
                        cursor=result.next_cursor,
                        page_size=result.executed_query.page_size,
                        range_start=1 if ref_count else 0,
                        range_end=ref_count,
                        total=result.total,
                    ),
                ),
            )

    @staticmethod
    def _runtime_metadata(channel_context: AgentChannelContext | None) -> dict[str, object]:
        if channel_context is None:
            return {"source": "web"}
        return {
            "source": channel_context.source,
            "provider": channel_context.provider,
            **channel_context.metadata,
        }

    @staticmethod
    def _workflow_replay_message_id(dispatch: RootDispatchResult) -> int | None:
        if not isinstance(dispatch, WorkflowDispatchResult):
            return None
        if dispatch.workflow_result.status != "REPLAY":
            return None
        return dispatch.workflow_result.message_id

    @staticmethod
    def _action_claim_id(
        prepared: _PreparedTurnInput,
        dispatch: RootDispatchResult,
    ) -> str | None:
        if prepared.entity_action_claim_id is not None:
            return prepared.entity_action_claim_id
        if isinstance(dispatch, (WorkflowDispatchResult, FailureDispatchResult)):
            return dispatch.action_claim_id
        return None

    @staticmethod
    def _action_claim_succeeded(dispatch: RootDispatchResult) -> bool:
        return (
            isinstance(dispatch, WorkflowDispatchResult)
            and dispatch.workflow_result.status in {"WAITING", "COMPLETED", "CANCELLED", "SKIPPED"}
        )

    def _settle_action_claim(
        self,
        db: Session,
        *,
        prepared: _PreparedTurnInput,
        dispatch: RootDispatchResult,
        team_id: int,
        user_id: int,
        session_id: int,
        client_request_id: UUID | str,
        result_message_id: int,
    ) -> None:
        action_claim_id = self._action_claim_id(prepared, dispatch)
        if action_claim_id is None:
            return
        if self._action_claim_succeeded(dispatch):
            self._complete_action_consumption(
                db,
                public_id=action_claim_id,
                team_id=team_id,
                user_id=user_id,
                session_id=session_id,
                client_request_id=client_request_id,
                result_message_id=result_message_id,
                submitted_values=(
                    prepared.root_input.values
                    if isinstance(prepared.root_input, InteractionTurnInput)
                    else None
                ),
            )
            return
        self.action_repository.release_consumption(
            db,
            public_id=action_claim_id,
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
            client_request_id=client_request_id,
        )

    def _complete_action_consumption(
        self,
        db: Session,
        *,
        public_id: str,
        team_id: int,
        user_id: int,
        session_id: int,
        client_request_id: UUID | str,
        result_message_id: int,
        submitted_values: dict[str, JsonValue] | None = None,
    ) -> None:
        """Make one successfully submitted action permanently read-only."""

        self.action_repository.begin_consumption(
            db,
            public_id=public_id,
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
            client_request_id=client_request_id,
        )
        self.action_repository.complete_consumption(
            db,
            public_id=public_id,
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
            client_request_id=client_request_id,
            result_message_id=result_message_id,
            submitted_values=submitted_values,
        )

    def _late_bind_durable_work(
        self,
        dispatch: RootDispatchResult,
        *,
        team_id: int,
        user_id: int,
        session_id: int,
        source_user_message_id: int,
        source_assistant_message_id: int,
    ) -> None:
        if not isinstance(dispatch, WorkflowDispatchResult):
            return
        receipts = dispatch.workflow_result.durable_work if dispatch.workflow_result.status == "COMPLETED" else []
        if not receipts:
            return
        bind_db = self.session_factory()
        try:
            self.durable_work_binder.bind(
                bind_db,
                receipts=receipts,
                binding=AgentAsyncOperationBinding(
                    team_id=team_id,
                    user_id=user_id,
                    session_id=session_id,
                    source_user_message_id=source_user_message_id,
                    source_assistant_message_id=source_assistant_message_id,
                ),
            )
            bind_db.commit()
        except Exception:
            bind_db.rollback()
            logger.exception(
                "Agent durable work late-bind failed: session_id=%s assistant_message_id=%s",
                session_id,
                source_assistant_message_id,
            )
        finally:
            bind_db.close()

    def _persist_interrupted_turn(
        self,
        db: Session,
        *,
        turn_start: AgentTurnStart | None,
        prepared: _PreparedTurnInput | None,
        team_id: int,
        user_id: int,
        session_id: int | None,
        client_request_id: UUID,
    ) -> None:
        if turn_start is None or session_id is None:
            return
        try:
            begin_result = self.turn_repository.begin(db, turn_start)
            if begin_result.outcome == "COMPLETED":
                db.rollback()
                return
            composition = self.ui_composer.compose(
                FailureDispatchResult(
                    error=AgentExecutionError(
                        code="TURN_INTERRUPTED",
                        message="本次操作已结束,请查看会话记录和后台任务状态。",
                        retryable=False,
                    )
                )
            )
            if prepared is not None and prepared.message_display == "STATE_UPDATE":
                composition = self._with_message_display(
                    composition,
                    display="STATE_UPDATE",
                )
            self.turn_repository.complete(
                db,
                AgentAssistantMessageCreate(
                    team_id=team_id,
                    user_id=user_id,
                    session_id=session_id,
                    turn_id=begin_result.user_message.turn_id,
                    content=composition.content,
                    ui=composition.body,
                    diagnostics={"dispatch_type": "failure", "error_code": "TURN_INTERRUPTED"},
                ),
            )
            self._release_prepared_action_claim(
                db,
                prepared=prepared,
                team_id=team_id,
                user_id=user_id,
                session_id=session_id,
                client_request_id=client_request_id,
            )
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Interrupted Agent turn persistence failed: session_id=%s", session_id)

    @staticmethod
    def _prepared_action_id(prepared: _PreparedTurnInput | None) -> str | None:
        if prepared is None:
            return None
        if prepared.entity_action_claim_id is not None:
            return prepared.entity_action_claim_id
        if isinstance(prepared.root_input, InteractionTurnInput):
            return prepared.root_input.action_id
        return None

    def _release_prepared_action_claim(
        self,
        db: Session,
        *,
        prepared: _PreparedTurnInput | None,
        team_id: int,
        user_id: int,
        session_id: int,
        client_request_id: UUID | str,
    ) -> None:
        action_id = self._prepared_action_id(prepared)
        if action_id is None:
            return
        action = self.action_repository.get_owned(
            db,
            public_id=action_id,
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
        )
        if (
            action is None
            or action.status != AgentUIActionStatus.CONSUMING
            or action.consumed_request_id != str(client_request_id)
        ):
            return
        self.action_repository.release_consumption(
            db,
            public_id=action_id,
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
            client_request_id=client_request_id,
        )

    @staticmethod
    def _dispatch_diagnostics(dispatch: RootDispatchResult) -> dict[str, object]:
        diagnostics: dict[str, object] = {"dispatch_type": dispatch.type}
        decision = getattr(dispatch, "decision", None)
        if decision is not None:
            diagnostics["decision"] = decision.model_dump(mode="json")
        if isinstance(dispatch, WorkflowDispatchResult) and dispatch.workflow_result.status == "COMPLETED":
            diagnostics["durable_work"] = [
                receipt.model_dump(mode="json")
                for receipt in dispatch.workflow_result.durable_work
            ]
        return diagnostics

    @staticmethod
    def _owned_assistant_message(
        db: Session,
        *,
        message_id: int,
        team_id: int,
        user_id: int,
        session_id: int,
    ) -> AgentMessage:
        message = (
            db.query(AgentMessage)
            .filter(
                AgentMessage.id == message_id,
                AgentMessage.team_id == team_id,
                AgentMessage.user_id == user_id,
                AgentMessage.session_id == session_id,
                AgentMessage.role == AgentMessageRole.ASSISTANT,
            )
            .one_or_none()
        )
        if message is None:
            raise AgentTurnIdempotencyConflictError("replay message is not owned by the action owner")
        return message

    @staticmethod
    def _message_ui(message: AgentMessage) -> AgentUIEnvelope:
        try:
            return AgentUIEnvelope.model_validate(message.ui_json)
        except ValidationError as exc:
            raise RuntimeError("persisted replay message has invalid Agent UI") from exc

    @staticmethod
    def _user_message_body(
        content: str,
        *,
        display: AgentUIMessageDisplay = "MESSAGE",
    ) -> AgentUIMessageBody:
        return AgentUIMessageBody(
            state="final",
            blocks=[
                TextBlock(
                    id="b_user_text_1",
                    type="text",
                    format="plain",
                    text=content,
                )
            ],
            suggested_actions=[],
            metadata=AgentUIMetadata(
                display=display,
                accessibility_label=content,
            ),
        )

    @staticmethod
    def _session_event(*, session_id: int, session_key: str) -> AgentSSEEventEnvelope:
        return AgentSSEEventEnvelope(
            root=AgentSSESessionEvent(
                event="session",
                session_id=session_id,
                session_key=session_key,
            )
        )

    @staticmethod
    def _done_event(*, session_id: int) -> AgentSSEEventEnvelope:
        return AgentSSEEventEnvelope(root=AgentSSEDoneEvent(event="done", session_id=session_id))

    def _progress_stream_event(
        self,
        progress: WorkflowProgress,
        *,
        turn_id: str,
        sequence: int,
    ) -> AgentSSEEventEnvelope:
        return AgentSSEEventEnvelope(
            root=AgentSSEAgentUIDeltaEvent(
                event="agent_ui",
                phase="delta",
                message_id=None,
                turn_id=turn_id,
                sequence=sequence,
                operations=[
                    UpsertBlockOperation(
                        op="upsert_block",
                        block=self.ui_composer.process_block(progress),
                    )
                ],
            )
        )

    @staticmethod
    def _final_stream_event(
        envelope: AgentUIEnvelope,
        *,
        sequence: int = 1,
    ) -> AgentSSEEventEnvelope:
        return AgentSSEEventEnvelope(
            root=AgentSSEAgentUIFinalEvent(
                event="agent_ui",
                phase="final",
                message_id=envelope.message_id,
                turn_id=envelope.turn_id,
                sequence=sequence,
                message=envelope,
            )
        )

    @staticmethod
    def _transport_error(
        *,
        code: AgentErrorCode,
        message: str,
        retryable: bool,
        session_id: int | None,
        status_code: int | None = None,
    ) -> AgentSSEEventEnvelope:
        return AgentSSEEventEnvelope(
            root=AgentSSETransportErrorEvent(
                event="transport_error",
                code=code,
                message=message,
                retryable=retryable,
                session_id=session_id,
                status_code=status_code,
            )
        )

    @staticmethod
    def _action_error(exc: Exception) -> tuple[AgentErrorCode, str]:
        if isinstance(exc, ActionAlreadyConsumedError):
            return "ACTION_ALREADY_CONSUMED", "该操作已被处理,请刷新会话查看最新结果。"
        if isinstance(exc, ActionExpiredError):
            return "ACTION_EXPIRED", "该操作已过期,请刷新会话后重新发起。"
        if isinstance(exc, EntityActionResultSetExpiredError):
            return "RESULT_SET_EXPIRED", "该查询结果已过期,请重新查询后再操作。"
        if isinstance(
            exc,
            (ActionNotFoundError, ActionOwnershipError, EntityActionPermissionDeniedError),
        ):
            return "PERMISSION_DENIED", "无权访问或执行该操作。"
        if isinstance(exc, EntityActionInvalidError):
            return "ACTION_INVALID", "提交的操作无效,请刷新会话后重试。"
        return "ACTION_INVALID", "提交的操作无效,请刷新会话后重试。"

    def _persist_action_error_turn(
        self,
        db: Session,
        *,
        request_input: AgentChatInput,
        client_request_id: UUID,
        input_fingerprint: str,
        team_id: int,
        user_id: int,
        session_id: int,
        code: AgentErrorCode,
        message: str,
    ) -> AgentUIEnvelope:
        if isinstance(request_input, InteractionSubmissionInput):
            presentation = self._interaction_submission_presentation(
                db,
                request_input=request_input,
                team_id=team_id,
                user_id=user_id,
                session_id=session_id,
            )
            user_content = presentation.content
            message_display = presentation.message_display
        else:
            user_content = "执行实体操作"
            message_display = "MESSAGE"
        begin_result = self.turn_repository.begin(
            db,
            AgentTurnStart(
                team_id=team_id,
                user_id=user_id,
                session_id=session_id,
                client_request_id=client_request_id,
                input_fingerprint=input_fingerprint,
                content=user_content,
                ui=self._user_message_body(
                    user_content,
                    display=message_display,
                ),
            ),
        )
        if begin_result.outcome == "COMPLETED":
            db.rollback()
            if begin_result.assistant_message is None:
                raise RuntimeError("completed action error turn is missing assistant message")
            return begin_result.assistant_message.ui
        # This handler owns the request that just failed. An IN_PROGRESS row is
        # therefore the already-committed user message created before Root
        # dispatch, not a reason to abandon the turn. Close it with one durable
        # error response so retries replay a final result instead of poisoning
        # the session with a permanent TURN_IN_PROGRESS state.
        composition = self.ui_composer.compose(
            FailureDispatchResult(
                error=AgentExecutionError(code=code, message=message, retryable=False)
            )
        )
        completed = self.turn_repository.complete(
            db,
            AgentAssistantMessageCreate(
                team_id=team_id,
                user_id=user_id,
                session_id=session_id,
                turn_id=begin_result.user_message.turn_id,
                content=composition.content,
                ui=composition.body,
                diagnostics={"dispatch_type": "failure", "error_code": code},
            ),
        )
        db.commit()
        return completed.message.ui

    @staticmethod
    def _request_input_fingerprint(request_input: AgentChatInput) -> str:
        canonical_input = json.dumps(
            request_input.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical_input.encode("utf-8")).hexdigest()


agent_application_service = AgentApplicationService(root_orchestrator=get_root_orchestrator())


def _load_agent_model_configs(
    db: Session,
    *,
    team_id: int,
) -> tuple[RootDecisionModelConfig, CRMQueryAgentModelConfig]:
    config = ai_config_crud.get_config(db, team_id)
    api_key = ai_config_crud.get_decrypted_api_key(db, team_id)
    if config is None or not isinstance(api_key, str) or not api_key.strip():
        raise HTTPException(
            status_code=503,
            detail="AI 模型配置不可用。请先完成团队 AI 配置。",
        )
    api_host = getattr(config, "api_host", None)
    model_name = getattr(config, "model_name", None)
    temperature = getattr(config, "temperature", None)
    if not isinstance(api_host, str) or not api_host.strip():
        raise HTTPException(status_code=503, detail="AI 模型地址配置无效。")
    if not isinstance(model_name, str) or not model_name.strip():
        raise HTTPException(status_code=503, detail="AI 模型名称配置无效。")
    if isinstance(temperature, bool) or not isinstance(temperature, (int, float)):
        raise HTTPException(status_code=503, detail="AI 模型温度配置无效。")
    enable_thinking = agent_model_enable_thinking(model_name)
    return (
        RootDecisionModelConfig(
            api_host=api_host,
            api_key=api_key,
            model=model_name,
            temperature=0,
            enable_thinking=enable_thinking,
        ),
        CRMQueryAgentModelConfig(
            api_host=api_host,
            api_key=api_key,
            model=model_name,
            temperature=float(temperature),
            enable_thinking=enable_thinking,
        ),
    )
