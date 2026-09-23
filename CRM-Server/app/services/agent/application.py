"""Channel-independent application boundary for CRM Agent turns."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from uuid import UUID
from datetime import timedelta
from time import monotonic
from typing import TYPE_CHECKING, Literal

from fastapi import HTTPException
from pydantic import JsonValue, TypeAdapter, ValidationError
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.security import create_access_token
from app.crud.team import user_team_crud
from app.core.database import SessionLocal
from app.crud.agent import agent_session_crud
from app.crud.ai_config import ai_config_crud
from app.crud.permission import permission_crud
from app.models.agent import AgentMessage, AgentMessageRole, AgentSession
from app.models.agent_persistence import AgentUIActionStatus
from app.models.agent_turn_execution import AgentTurnExecution, AgentTurnExecutionStatus
from app.models.user import User, UserStatus
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
from app.services.agent.input import AgentChannelContext
from app.services.agent import agent_copy
from app.services.agent.durable_work import AgentDurableWorkBinder, agent_durable_work_binder
from app.services.agent.durable_work_contracts import AgentAsyncOperationBinding
from app.services.agent.langchain_runtime import agent_model_enable_thinking
from app.services.agent.orchestrator import (
    AgentExecutionError,
    FailureDispatchResult,
    InteractionTurnInput,
    QueryDispatchResult,
    RootConversationMemory,
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
from app.services.agent.run_log import build_turn_timeline
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
from app.services.agent.workflow.contracts import WorkflowCommittedResource

from app.utils.public_id import generate_public_id
from app.utils.time import business_now


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


@dataclass(frozen=True)
class _AcceptedExecution:
    execution_id: int
    session_id: int
    session_key: str
    turn_id: str
    user_message_id: int
    immediate_events: tuple[AgentSSEEventEnvelope, ...] = ()


@dataclass(frozen=True)
class AgentRequestStatus:
    status: RequestStatusName
    message: AgentUIEnvelope | None = None


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
        self._failure_events: dict[int, AgentUIEnvelope] = {}
        self.ui_composer = ui_composer or AgentUIComposer()
        self.durable_work_binder = durable_work_binder or agent_durable_work_binder
        self._progress_events: dict[int, list[AgentSSEEventEnvelope]] = {}
        self._workers: dict[int, asyncio.Task[None]] = {}

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
        """Accept one typed turn durably, then observe its detached execution."""

        accepted = await asyncio.to_thread(
            self._accept_turn,
            request_input=request_input,
            client_request_id=client_request_id,
            channel_context=channel_context,
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
            session_key=session_key,
        )
        self._ensure_worker(accepted.execution_id, authorization)
        for event in accepted.immediate_events:
            yield event
            if event.root.event == "done":
                return
        deadline = monotonic() + get_settings().AGENT_TIMEOUT + 5
        sequence = 0
        while monotonic() < deadline:
            progress_events = self._progress_events.get(accepted.execution_id, [])
            while sequence < len(progress_events):
                yield progress_events[sequence]
                sequence += 1
            await asyncio.sleep(0.01)
            status = self.request_status(
                team_id=team_id, user_id=user_id, session_id=accepted.session_id,
                client_request_id=client_request_id,
            )
            if status.status != "IN_PROGRESS":
                while sequence < len(self._progress_events.get(accepted.execution_id, [])):
                    yield self._progress_events[accepted.execution_id][sequence]
                    sequence += 1
                failure_message = self._failure_events.pop(accepted.execution_id, None)
                message = failure_message or status.message
                if message is not None:
                    sequence += 1
                    yield self._final_stream_event(message, sequence=sequence)
                self._progress_events.pop(accepted.execution_id, None)
                worker = self._workers.pop(accepted.execution_id, None)
                if worker is not None:
                    await worker
                yield self._done_event(session_id=accepted.session_id)
                return
        yield self._transport_error(
            code="TURN_IN_PROGRESS",
            message="请求已受理，连接结束后仍会继续执行。",
            retryable=True,
            session_id=accepted.session_id,
        )
        yield self._done_event(session_id=accepted.session_id)

    def request_status(
        self,
        *,
        team_id: int,
        user_id: int,
        session_id: int,
        client_request_id: UUID,
    ) -> AgentRequestStatus:
        """Return the exact durable outcome for one owned client request."""

        db = self.session_factory()
        try:
            execution = self._owned_execution(
                db,
                team_id=team_id,
                user_id=user_id,
                session_id=session_id,
                client_request_id=str(client_request_id),
            )
            if execution is None:
                raise HTTPException(status_code=404, detail="请求不存在")
            message = None
            if execution.result_message_id is not None:
                persisted = self._owned_assistant_message(
                    db,
                    message_id=execution.result_message_id,
                    team_id=team_id,
                    user_id=user_id,
                    session_id=session_id,
                )
                message = self._message_ui(persisted)
            return AgentRequestStatus(status=self._public_status(execution.status), message=message)
        finally:
            db.close()

    async def recover_expired_executions(self, *, limit: int | None = None) -> dict[str, int]:
        """Reacquire expired leases after rechecking identity, membership, and permissions."""

        settings = get_settings()
        db = self.session_factory()
        acquired: list[tuple[int, str]] = []
        try:
            rows = (
                db.query(AgentTurnExecution)
                .filter(
                    AgentTurnExecution.status.in_(
                        [AgentTurnExecutionStatus.ACCEPTED, AgentTurnExecutionStatus.RUNNING]
                    ),
                    AgentTurnExecution.lease_expires_at.is_not(None),
                    AgentTurnExecution.lease_expires_at <= business_now(),
                )
                .order_by(AgentTurnExecution.id.asc())
                .limit(limit or settings.AGENT_TURN_RECOVERY_BATCH_SIZE)
                .all()
            )
            for row in rows:
                if not self._recovery_authorization_still_valid(db, row):
                    self._mark_reauthorization_failed(row)
                    continue
                if int(row.attempt_count) >= settings.AGENT_TURN_EXECUTION_MAX_ATTEMPTS:
                    self._mark_attempt_limit(row)
                    continue
                owner = uuid.uuid4().hex
                claimed = self._claim_execution(
                    db, int(row.id), expected_version=int(row.lease_version), owner=owner
                )
                if claimed is not None:
                    acquired.append((int(claimed.id), owner))
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
        for execution_id, owner in acquired:
            self._ensure_worker(execution_id, None, recovery_owner=owner)
        return {"recovered": len(acquired)}

    def _accept_turn(
        self,
        *,
        request_input: AgentChatInput,
        client_request_id: UUID,
        channel_context: AgentChannelContext | None,
        team_id: int,
        user_id: int,
        session_id: int | None,
        session_key: str | None,
    ) -> _AcceptedExecution:
        db = self.session_factory()
        session = None
        fingerprint = self._request_input_fingerprint(request_input)
        try:
            session = self._owned_or_new_session(
                db,
                team_id=team_id,
                user_id=user_id,
                request_input=request_input,
                session_id=session_id,
                session_key=session_key,
            )
            effective_session_id = int(session.id)
            session_event = self._session_event(
                session_id=effective_session_id, session_key=str(session.session_key)
            )
            permissions = self._current_permission_codes(db, team_id=team_id, user_id=user_id)
            prepared = self._prepare_turn_input(
                db,
                request_input=request_input,
                team_id=team_id,
                user_id=user_id,
                session_id=effective_session_id,
                client_request_id=client_request_id,
                permission_codes=permissions,
            )
            begin = self.turn_repository.begin(
                db,
                AgentTurnStart(
                    team_id=team_id,
                    user_id=user_id,
                    session_id=effective_session_id,
                    client_request_id=client_request_id,
                    input_fingerprint=fingerprint,
                    content=prepared.content,
                    ui=self._user_message_body(prepared.content, display=prepared.message_display),
                ),
            )
            if begin.outcome == "COMPLETED":
                if begin.assistant_message is None:
                    raise RuntimeError("completed turn is missing assistant message")
                db.rollback()
                return self._immediate(
                    session, begin.user_message.turn_id, begin.user_message.id, session_event,
                    self._final_stream_event(begin.assistant_message.ui),
                )
            if prepared.replay_message_id is not None:
                replay = self._owned_assistant_message(
                    db,
                    message_id=prepared.replay_message_id,
                    team_id=team_id,
                    user_id=user_id,
                    session_id=effective_session_id,
                )
                db.rollback()
                return self._immediate(
                    session, begin.user_message.turn_id, begin.user_message.id, session_event,
                    self._final_stream_event(self._message_ui(replay)),
                )
            existing = self._owned_execution(
                db,
                team_id=team_id,
                user_id=user_id,
                session_id=effective_session_id,
                client_request_id=str(client_request_id),
            )
            if existing is None:
                existing = self._new_execution(
                    session_id=effective_session_id,
                    turn_id=begin.user_message.turn_id,
                    team_id=team_id,
                    user_id=user_id,
                    client_request_id=str(client_request_id),
                    fingerprint=fingerprint,
                    request_input=request_input,
                    prepared=prepared,
                    permissions=permissions,
                    channel_context=channel_context,
                )
                try:
                    with db.begin_nested():
                        db.add(existing)
                        db.flush()
                except IntegrityError:
                    existing = self._owned_execution(
                        db,
                        team_id=team_id,
                        user_id=user_id,
                        session_id=effective_session_id,
                        client_request_id=str(client_request_id),
                    )
                    if existing is None:
                        raise
            elif existing.input_fingerprint != fingerprint:
                raise AgentTurnIdempotencyConflictError("client_request_id reused")
            db.commit()
            return _AcceptedExecution(
                int(existing.id),
                effective_session_id,
                str(session.session_key),
                begin.user_message.turn_id,
                begin.user_message.id,
                (session_event,),
            )
        except AgentTurnIdempotencyConflictError:
            db.rollback()
            if session is None:
                raise
            return self._immediate(
                session,
                "",
                0,
                self._session_event(session_id=int(session.id), session_key=str(session.session_key)),
                self._transport_error(
                    code="IDEMPOTENCY_KEY_REUSED",
                    message="client_request_id 已用于不同输入。",
                    retryable=False,
                    session_id=int(session.id),
                ),
            )
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
                raise
            code, message = self._action_error(exc)
            envelope = self._persist_action_error_turn(
                db,
                request_input=request_input,
                client_request_id=client_request_id,
                input_fingerprint=fingerprint,
                team_id=team_id,
                user_id=user_id,
                session_id=int(session.id),
                code=code,
                message=message,
            )
            return self._immediate(
                session,
                envelope.turn_id,
                0,
                self._session_event(session_id=int(session.id), session_key=str(session.session_key)),
                self._final_stream_event(envelope),
            )
        finally:
            db.close()

    def _ensure_worker(
        self,
        execution_id: int,
        authorization: str | None,
        *,
        recovery_owner: str | None = None,
    ) -> None:
        if execution_id <= 0:
            return
        current = self._workers.get(execution_id)
        if current is not None and not current.done():
            return
        self._workers[execution_id] = asyncio.create_task(
            self._run_execution(execution_id, authorization, recovery_owner)
        )

    async def _run_execution(
        self,
        execution_id: int,
        authorization: str | None,
        recovery_owner: str | None,
    ) -> None:
        db = self.session_factory()
        owner = recovery_owner or uuid.uuid4().hex
        runtime: RootRuntimeContext | None = None
        turn_identity = (0, 0, 0, "00000000-0000-0000-0000-000000000000")
        try:
            execution = db.get(AgentTurnExecution, execution_id)
            if execution is None or execution.status not in {
                AgentTurnExecutionStatus.ACCEPTED,
                AgentTurnExecutionStatus.RUNNING,
            }:
                return
            if recovery_owner is None:
                execution = self._claim_execution(
                    db, execution_id, expected_version=int(execution.lease_version), owner=owner
                )
                db.commit()
            if execution is None or execution.lease_owner != owner:
                db.rollback()
                return
            if recovery_owner is not None and not self._recovery_authorization_still_valid(db, execution):
                self._mark_reauthorization_failed(execution)
                db.commit()
                return
            prepared = self._prepared_from_execution(execution)
            root_model, query_model = _load_agent_model_configs(db, team_id=execution.team_id)
            current_permissions = self._current_permission_codes(
                db, team_id=execution.team_id, user_id=execution.user_id
            )
            granted = set(execution.permission_codes_json)
            if not current_permissions.issuperset(granted):
                self._mark_reauthorization_failed(execution)
                db.commit()
                return
            worker_authorization = self._worker_authorization(execution)
            turn_identity = (
                int(execution.team_id), int(execution.user_id), int(execution.session_id), execution.client_request_id
            )
            turn_id = execution.turn_id
            metadata = self._runtime_metadata_from_execution(execution)
            claimed_execution_id = int(execution.id)
            claimed_lease_version = int(execution.lease_version)
            sequence = 0

            def record_progress(progress: WorkflowProgress) -> None:
                nonlocal sequence
                sequence += 1
                self._progress_events.setdefault(execution_id, []).append(
                    self._progress_stream_event(progress, turn_id=turn_id, sequence=sequence)
                )

            db.commit()
            runtime = RootRuntimeContext(
                db=db, authorization=worker_authorization, permission_codes=frozenset(granted),
                root_model_config=root_model, query_model_config=query_model, metadata=metadata,
                deadline_at=monotonic() + get_settings().AGENT_TIMEOUT,
            )
            dispatch = await self.root_orchestrator.dispatch(
                RootTurnInput(
                    team_id=turn_identity[0], user_id=turn_identity[1], session_id=turn_identity[2],
                    client_request_id=turn_identity[3], input=prepared.root_input,
                    selected_entity_ref=prepared.selected_entity_ref,
                ),
                runtime=runtime,
                on_progress=record_progress,
            )
            claim_id = runtime.metadata.get("text_resume_action_claim_id")
            if isinstance(claim_id, str):
                execution = db.get(AgentTurnExecution, execution_id)
                if execution is not None and execution.lease_owner == owner:
                    execution.entity_action_claim_id = claim_id
                    db.flush()
            self._settle_execution(
                db, execution_id=claimed_execution_id, lease_version=claimed_lease_version,
                owner=owner, prepared=prepared, dispatch=dispatch,
            )
        except Exception as exc:
            owns_lease = False
            try:
                db.rollback()
                current = db.get(AgentTurnExecution, execution_id)
                owns_lease = current is not None and current.lease_owner == owner
            except Exception:
                db.rollback()
                owns_lease = False
            if not owns_lease:
                return
            claim_id = runtime.metadata.get("text_resume_action_claim_id") if runtime is not None else None
            if isinstance(claim_id, str):
                execution = db.get(AgentTurnExecution, execution_id)
                if execution is not None and execution.lease_owner == owner:
                    execution.entity_action_claim_id = claim_id
                    db.commit()
            logger.exception("Durable Agent execution failed: execution_id=%s", execution_id)
            self._settle_unknown_failure(execution_id, owner, exc)
            status = self.request_status(
                team_id=turn_identity[0], user_id=turn_identity[1], session_id=turn_identity[2],
                client_request_id=UUID(turn_identity[3]),
            )
            if status.message is not None:
                self._failure_events[execution_id] = status.message
        finally:
            db.close()

    def _settle_execution(
        self,
        db: Session,
        *,
        execution_id: int,
        lease_version: int,
        owner: str,
        prepared: _PreparedTurnInput,
        dispatch: RootDispatchResult,
    ) -> None:
        current = self._locked_execution(db, execution_id)
        if current is None or current.lease_owner != owner or int(current.lease_version) != lease_version:
            db.rollback()
            return
        try:
            completed = None
            if isinstance(dispatch, QueryDispatchResult):
                dispatch = self._sign_query_result_sets(dispatch)
            replay_message_id = self._workflow_replay_message_id(dispatch)
            if replay_message_id is not None:
                self._finish_execution(
                    current, status=AgentTurnExecutionStatus.COMPLETED,
                    result_message_id=replay_message_id, dispatch=dispatch,
                )
                db.commit()
                return
            with db.begin_nested():
                composition = self.ui_composer.compose(dispatch)
                if prepared.message_display == "STATE_UPDATE":
                    composition = self._with_message_display(composition, display="STATE_UPDATE")
                completed = self.turn_repository.complete(
                    db,
                    AgentAssistantMessageCreate(
                        team_id=current.team_id, user_id=current.user_id, session_id=current.session_id,
                        turn_id=current.turn_id, content=composition.content, ui=composition.body,
                        diagnostics=self._dispatch_diagnostics(dispatch, user_text=prepared.content),
                    ),
                )
                if isinstance(dispatch, QueryDispatchResult):
                    self._persist_query_result_sets(
                        db, query_result=dispatch.query_result, team_id=current.team_id, user_id=current.user_id,
                        session_id=current.session_id, source_message_id=completed.message.id,
                    )
                for draft in composition.action_drafts:
                    self.action_repository.register(
                        db,
                        AgentUIActionRegistration(
                            public_id=draft.public_id, team_id=current.team_id, user_id=current.user_id,
                            session_id=current.session_id, message_id=completed.message.id, action_type=draft.action_type,
                            root_context_role=draft.root_context_role,
                            target=TypeAdapter(dict[str, JsonValue]).dump_python(draft.target, mode="json"),
                            consumption_mode=draft.consumption_mode,
                        ),
                    )
                self._settle_action_claim(
                    db, prepared=prepared, dispatch=dispatch, team_id=current.team_id, user_id=current.user_id,
                    session_id=current.session_id, client_request_id=current.client_request_id, result_message_id=completed.message.id,
                )
                self._finish_execution(
                    current, status=self._execution_status(dispatch), result_message_id=completed.message.id, dispatch=dispatch,
                )
            db.commit()
        except Exception:
            db.rollback()
            raise
        if completed is not None:
            self._late_bind_durable_work(
                dispatch, team_id=current.team_id, user_id=current.user_id, session_id=current.session_id,
                source_user_message_id=self._user_message_id(db, current), source_assistant_message_id=completed.message.id,
            )

    def _settle_unknown_failure(self, execution_id: int, owner: str, exc: Exception) -> None:
        db = self.session_factory()
        db.begin()
        try:
            current = self._locked_execution(db, execution_id)
            if current is None or current.lease_owner != owner:
                db.rollback()
                return
            if isinstance(exc, (ActionAlreadyConsumedError, ActionExpiredError, ActionUnavailableError, ActionNotFoundError, ActionOwnershipError)):
                code, message = self._action_error(exc)
                failure = FailureDispatchResult(error=AgentExecutionError(code=code, message=message, retryable=False))
            else:
                failure = FailureDispatchResult(
                    error=AgentExecutionError(code="INTERNAL_ERROR", message=agent_copy.service_error(str(exc)), retryable=True)
                )
            prepared = self._prepared_from_execution(current)
            composition = self.ui_composer.compose(failure)
            if prepared.message_display == "STATE_UPDATE":
                composition = self._with_message_display(composition, display="STATE_UPDATE")
            completed = self.turn_repository.complete(
                db,
                AgentAssistantMessageCreate(
                    team_id=current.team_id, user_id=current.user_id, session_id=current.session_id,
                    turn_id=current.turn_id, content=composition.content, ui=composition.body,
                    diagnostics=self._dispatch_diagnostics(failure, user_text=prepared.content),
                ),
            )
            self._release_prepared_action_claim(
                db, prepared=prepared, team_id=current.team_id, user_id=current.user_id,
                session_id=current.session_id, client_request_id=current.client_request_id,
            )
            self._finish_execution(
                current, status=AgentTurnExecutionStatus.FAILED, result_message_id=completed.message.id, dispatch=failure,
            )
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Durable Agent failure settlement failed: execution_id=%s", execution_id)
        finally:
            db.close()
    @staticmethod
    def _immediate(session, turn_id: str, user_message_id: int, *events: AgentSSEEventEnvelope) -> _AcceptedExecution:
        return _AcceptedExecution(
            0, int(session.id), str(session.session_key), turn_id, user_message_id,
            (*events, AgentApplicationService._done_event(session_id=int(session.id))),
        )

    @staticmethod
    def _new_execution(**values: object) -> AgentTurnExecution:
        request_input = values["request_input"]
        prepared = values["prepared"]
        permissions = values["permissions"]
        channel_context = values["channel_context"]
        if not isinstance(request_input, (TextAgentInput, InteractionSubmissionInput, EntityActionInput)):
            raise TypeError("unsupported Agent input")
        if not isinstance(prepared, _PreparedTurnInput) or not isinstance(permissions, frozenset):
            raise TypeError("invalid execution snapshot")
        now = business_now()
        return AgentTurnExecution(
            team_id=int(values["team_id"]), user_id=int(values["user_id"]), session_id=int(values["session_id"]),
            turn_id=str(values["turn_id"]), client_request_id=str(values["client_request_id"]),
            input_fingerprint=str(values["fingerprint"]), request_input_json=request_input.model_dump(mode="json"),
            root_input_json=prepared.root_input.model_dump(mode="json"), permission_codes_json=sorted(permissions),
            channel_context_json=AgentApplicationService._channel_payload(channel_context if isinstance(channel_context, AgentChannelContext) or channel_context is None else None),
            selected_entity_ref_json=prepared.selected_entity_ref.model_dump(mode="json") if prepared.selected_entity_ref else None,
            message_display=prepared.message_display, entity_action_claim_id=prepared.entity_action_claim_id,
            status=AgentTurnExecutionStatus.ACCEPTED, lease_version=0, committed_resources_json=[],
            completed_command_ids_json=[], created_time=now, last_modified_time=now,
        )

    def _claim_execution(self, db: Session, execution_id: int, *, expected_version: int, owner: str) -> AgentTurnExecution | None:
        row = self._locked_execution(db, execution_id)
        if row is None or int(row.lease_version) != expected_version:
            return None
        if row.status not in {AgentTurnExecutionStatus.ACCEPTED, AgentTurnExecutionStatus.RUNNING}:
            return None
        row.status = AgentTurnExecutionStatus.RUNNING
        row.lease_version = expected_version + 1
        row.lease_owner = owner
        row.lease_expires_at = business_now() + timedelta(seconds=get_settings().AGENT_TURN_EXECUTION_LEASE_SECONDS)
        row.attempt_count = int(row.attempt_count) + 1
        row.last_modified_time = business_now()
        db.flush()
        return row

    @staticmethod
    def _finish_execution(execution: AgentTurnExecution, *, status: str, result_message_id: int, dispatch: RootDispatchResult) -> None:
        resources, commands, failed_command = AgentApplicationService._business_facts(dispatch)
        execution.status = status
        execution.result_message_id = result_message_id
        execution.committed_resources_json = [item.model_dump(mode="json") for item in resources]
        execution.completed_command_ids_json = commands
        execution.failed_command_id = failed_command
        execution.lease_owner = None
        execution.lease_expires_at = None
        execution.last_modified_time = business_now()

    def _owned_or_new_session(self, db: Session, *, team_id: int, user_id: int, request_input: AgentChatInput, session_id: int | None, session_key: str | None):
        if session_id or session_key:
            return require_owned_session(db, team_id=team_id, user_id=user_id, session_id=session_id, session_key=session_key)
        title = request_input.text if isinstance(request_input, TextAgentInput) else "Agent 会话"
        return agent_session_crud.create(db, AgentSessionCreate(session_key=new_session_key(), team_id=team_id, user_id=user_id, title=title[:50]))

    @staticmethod
    def _current_permission_codes(db: Session, *, team_id: int, user_id: int) -> frozenset[str]:
        return frozenset(
            permission.code for permission in permission_crud.get_user_permissions(db, user_id=user_id, team_id=team_id)
            if isinstance(getattr(permission, "code", None), str) and permission.code
        )

    @staticmethod
    def _channel_payload(channel_context: AgentChannelContext | None) -> dict[str, JsonValue]:
        if channel_context is None:
            return {"source": "web", "provider": None, "metadata": {}}
        metadata = {
            key: value for key, value in channel_context.metadata.items()
            if isinstance(value, (str, int, float, bool)) or value is None
        }
        return {"source": channel_context.source, "provider": channel_context.provider, "metadata": metadata}

    @staticmethod
    def _prepared_from_execution(execution: AgentTurnExecution) -> _PreparedTurnInput:
        payload = execution.root_input_json
        root_input = (
            InteractionTurnInput.model_validate(payload) if payload.get("type") == "interaction"
            else TextTurnInput.model_validate(payload)
        )
        selected = EntityRef.model_validate(execution.selected_entity_ref_json) if execution.selected_entity_ref_json else None
        text = execution.request_input_json.get("text")
        return _PreparedTurnInput(
            text if isinstance(text, str) else "已提交", root_input, execution.message_display, selected, execution.entity_action_claim_id,
        )

    @staticmethod
    def _runtime_metadata_from_execution(execution: AgentTurnExecution) -> dict[str, object]:
        metadata: dict[str, object] = {"source": execution.channel_context_json.get("source", "web")}
        provider = execution.channel_context_json.get("provider")
        if isinstance(provider, str):
            metadata["provider"] = provider
        extra = execution.channel_context_json.get("metadata")
        if isinstance(extra, dict):
            metadata.update(extra)
        return metadata

    @staticmethod
    def _worker_authorization(execution: AgentTurnExecution) -> str:
        token = create_access_token(
            {
                "sub": str(execution.user_id), "team_id": execution.team_id, "purpose": "agent_worker",
                "execution_id": execution.public_id, "lease_version": execution.lease_version,
                "permissions": sorted(set(execution.permission_codes_json)),
            },
            expires_delta=timedelta(seconds=get_settings().AGENT_WORKER_TOKEN_SECONDS),
        )
        return f"Bearer {token}"

    def _recovery_authorization_still_valid(self, db: Session, execution: AgentTurnExecution) -> bool:
        user = db.get(User, execution.user_id)
        if user is None or user.status != UserStatus.ACTIVE:
            return False
        if user_team_crud.get_by_user_and_team(db, execution.user_id, execution.team_id) is None:
            return False
        current = self._current_permission_codes(db, team_id=execution.team_id, user_id=execution.user_id)
        return current.issuperset(set(execution.permission_codes_json))

    @staticmethod
    def _mark_reauthorization_failed(execution: AgentTurnExecution) -> None:
        execution.status = AgentTurnExecutionStatus.FAILED
        execution.last_error_code = "REAUTHORIZATION_FAILED"
        execution.lease_owner = None
        execution.lease_expires_at = None
        execution.last_modified_time = business_now()

    @staticmethod
    def _mark_attempt_limit(execution: AgentTurnExecution) -> None:
        execution.status = AgentTurnExecutionStatus.NEEDS_RECONCILIATION
        execution.last_error_code = "ATTEMPT_LIMIT_REACHED"
        execution.lease_owner = None
        execution.lease_expires_at = None
        execution.last_modified_time = business_now()

    @staticmethod
    def _owned_execution(db: Session, *, team_id: int, user_id: int, session_id: int, client_request_id: str) -> AgentTurnExecution | None:
        return db.query(AgentTurnExecution).filter_by(
            team_id=team_id, user_id=user_id, session_id=session_id, client_request_id=client_request_id
        ).one_or_none()

    @staticmethod
    def _locked_execution(db: Session, execution_id: int) -> AgentTurnExecution | None:
        return db.query(AgentTurnExecution).filter_by(id=execution_id).populate_existing().with_for_update().one_or_none()

    @staticmethod
    def _user_message_id(db: Session, execution: AgentTurnExecution) -> int:
        return int(db.query(AgentMessage).filter_by(session_id=execution.session_id, turn_id=execution.turn_id, role=AgentMessageRole.USER).one().id)

    @staticmethod
    def _public_status(status: str) -> RequestStatusName:
        if status in {AgentTurnExecutionStatus.ACCEPTED, AgentTurnExecutionStatus.RUNNING}:
            return "IN_PROGRESS"
        if status in {
            AgentTurnExecutionStatus.COMPLETED, AgentTurnExecutionStatus.PARTIALLY_COMMITTED,
            AgentTurnExecutionStatus.NEEDS_RECONCILIATION,
        }:
            return status
        return "FAILED"

    @staticmethod
    def _execution_status(dispatch: RootDispatchResult) -> str:
        if isinstance(dispatch, FailureDispatchResult):
            return AgentTurnExecutionStatus.FAILED
        if not isinstance(dispatch, WorkflowDispatchResult) or dispatch.workflow_result.status != "FAILED":
            return AgentTurnExecutionStatus.COMPLETED
        result = dispatch.workflow_result
        if result.committed_resources or result.completed_command_ids or result.durable_work:
            return AgentTurnExecutionStatus.PARTIALLY_COMMITTED
        return AgentTurnExecutionStatus.NEEDS_RECONCILIATION if result.retryable else AgentTurnExecutionStatus.FAILED

    @staticmethod
    def _business_facts(dispatch: RootDispatchResult) -> tuple[list[WorkflowCommittedResource], list[str], str | None]:
        if not isinstance(dispatch, WorkflowDispatchResult) or dispatch.workflow_result.status != "FAILED":
            return [], [], None
        result = dispatch.workflow_result
        return list(result.committed_resources), list(result.completed_command_ids), result.failed_command_id

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
            "STATE_UPDATE" if target.get("result_display") == "STATE_UPDATE" else "MESSAGE"
        )
        if self._is_signed_follow_up_content_cancel(target, request_input.values):
            return _InteractionSubmissionPresentation(
                content="取消",
                message_display=message_display,
            )
        interaction_type = target.get("interaction_type")
        submit_on_select = target.get("submit_on_select") is True
        if interaction_type == "confirmation" or (interaction_type == "choice" and submit_on_select):
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
            content=(submit_label.strip() if isinstance(submit_label, str) and submit_label.strip() else "已提交"),
            message_display=message_display,
        )

    @staticmethod
    def _is_signed_follow_up_content_cancel(target: dict[str, JsonValue], values: dict[str, JsonValue]) -> bool:
        return (
            len(values) == 1
            and values.get("cancel") is True
            and target.get("allow_cancel") is True
            and target.get("business_action") == "provide_follow_up_content"
            and target.get("interaction_type") in {"text_input", "form"}
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
                raise RuntimeError("completed CRM query result requires an executed query")
            result_set_id = result.result_set_id or generate_public_id("rs")
            signed_results.append(
                result.model_copy(
                    update={
                        "result_set_id": result_set_id,
                        "entity_refs": [
                            ref.model_copy(update={"result_set_id": result_set_id}) for ref in result.entity_refs
                        ],
                    }
                )
            )
        return dispatch.model_copy(
            update={"query_result": dispatch.query_result.model_copy(update={"query_results": signed_results})}
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
                raise RuntimeError("completed CRM query result requires a server-issued result set and executed query")
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
        if not isinstance(dispatch, WorkflowDispatchResult):
            return False
        result = dispatch.workflow_result
        if result.status in {"WAITING", "COMPLETED", "CANCELLED", "SKIPPED"}:
            return True
        if result.status != "FAILED" or result.retryable:
            return False
        return not (result.committed_resources or result.completed_command_ids or result.durable_work)

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
        cancelled_follow_up = False
        if (
            isinstance(dispatch, WorkflowDispatchResult)
            and dispatch.workflow_result.status == "CANCELLED"
            and isinstance(prepared.root_input, InteractionTurnInput)
            and prepared.root_input.action_id == action_claim_id
        ):
            action = self.action_repository.get_owned(
                db,
                public_id=action_claim_id,
                team_id=team_id,
                user_id=user_id,
                session_id=session_id,
            )
            cancelled_follow_up = (
                action is not None
                and action.action_type == "submit_interaction"
                and self._is_signed_follow_up_content_cancel(action.target, prepared.root_input.values)
            )
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
                    prepared.root_input.values if isinstance(prepared.root_input, InteractionTurnInput) else None
                ),
                cancelled=cancelled_follow_up,
            )
            if cancelled_follow_up:
                session = (
                    db.query(AgentSession)
                    .filter_by(id=session_id, team_id=team_id, user_id=user_id)
                    .populate_existing()
                    .with_for_update()
                    .one()
                )
                context = dict(session.context_json) if isinstance(session.context_json, dict) else {}
                context["_root_conversation_memory"] = RootConversationMemory().model_dump(
                    mode="json", exclude_none=True
                )
                context["recent_messages_after_id"] = result_message_id
                session.context_json = context
                db.flush()
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
        cancelled: bool = False,
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
            cancelled=cancelled,
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
        receipts = getattr(dispatch.workflow_result, "durable_work", []) or []
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
        runtime_context: RootRuntimeContext | None,
    ) -> None:
        if turn_start is None or session_id is None:
            return
        try:
            begin_result = self.turn_repository.begin(db, turn_start)
            if begin_result.outcome == "COMPLETED":
                db.rollback()
                return
            failure = FailureDispatchResult(
                error=AgentExecutionError(
                    code="TURN_INTERRUPTED",
                    message="本次操作已结束,请查看会话记录和后台任务状态。",
                    retryable=False,
                )
            )
            composition = self.ui_composer.compose(failure)
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
                    diagnostics=self._dispatch_diagnostics(
                        failure,
                        user_text=prepared.content if prepared is not None else composition.content,
                    ),
                ),
            )
            self._release_prepared_action_claim(
                db,
                prepared=prepared,
                team_id=team_id,
                user_id=user_id,
                session_id=session_id,
                client_request_id=client_request_id,
                runtime_context=runtime_context,
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
        runtime_context: RootRuntimeContext | None = None,
    ) -> None:
        action_id = self._prepared_action_id(prepared)
        if action_id is None and runtime_context is not None:
            claim_id = runtime_context.metadata.get("text_resume_action_claim_id")
            if isinstance(claim_id, str):
                action_id = claim_id
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
    def _dispatch_diagnostics(dispatch: RootDispatchResult, *, user_text: str) -> dict[str, object]:
        diagnostics: dict[str, object] = {"dispatch_type": dispatch.type}
        decision = getattr(dispatch, "decision", None)
        if decision is not None:
            diagnostics["decision"] = decision.model_dump(mode="json")
        receipts = getattr(getattr(dispatch, "workflow_result", None), "durable_work", None)
        if receipts:
            diagnostics["durable_work"] = [receipt.model_dump(mode="json") for receipt in receipts]
        diagnostics["turn_observability"] = build_turn_timeline(
            dispatch,
            user_text=user_text,
        ).model_dump(mode="json")
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
        failure = FailureDispatchResult(error=AgentExecutionError(code=code, message=message, retryable=False))
        composition = self.ui_composer.compose(failure)
        completed = self.turn_repository.complete(
            db,
            AgentAssistantMessageCreate(
                team_id=team_id,
                user_id=user_id,
                session_id=session_id,
                turn_id=begin_result.user_message.turn_id,
                content=composition.content,
                ui=composition.body,
                diagnostics=self._dispatch_diagnostics(failure, user_text=user_content),
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
    raw_max_tokens = getattr(config, "max_tokens", None)
    max_tokens = (
        raw_max_tokens
        if isinstance(raw_max_tokens, int) and not isinstance(raw_max_tokens, bool) and raw_max_tokens > 0
        else None
    )
    return (
        RootDecisionModelConfig(
            api_host=api_host,
            api_key=api_key,
            model=model_name,
            temperature=0,
            enable_thinking=enable_thinking,
            max_tokens=max_tokens,
        ),
        CRMQueryAgentModelConfig(
            api_host=api_host,
            api_key=api_key,
            model=model_name,
            temperature=float(temperature),
            enable_thinking=enable_thinking,
            max_tokens=max_tokens,
        ),
    )
