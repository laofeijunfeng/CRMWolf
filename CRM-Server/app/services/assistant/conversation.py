"""Conversation orchestration over the existing task/turn/CRM atomic boundaries."""
# ruff: noqa: RUF001 -- Chinese user-facing copy uses native punctuation.

from __future__ import annotations

from datetime import datetime, timedelta
from time import monotonic
from typing import TYPE_CHECKING, Protocol

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import is_database_schema_mismatch
from app.core.logging import get_logger
from app.crud import assistant_conversation as crud
from app.schemas.assistant import AssistantTaskView, SubmitInputRequest
from app.schemas.assistant_conversation import (
    ConversationBoundary,
    ConversationChoiceRequest,
    ConversationCommandRequest,
    ConversationDecision,
    ConversationDispositionProjection,
    ConversationKindRequest,
    ConversationLink,
    ConversationMessage,
    ConversationProjection,
    ConversationReply,
    ConversationTextRequest,
    ConversationView,
    PreparedSubmission,
)
from app.services.assistant.contracts import (
    AcceptedProposalReceipt,
    DraftField,
    EntityCreateReceipt,
    TaskAuthority,
    TaskDraft,
)
from app.services.assistant.conversation_router import ConversationRootClassifier
from app.services.assistant.failure_contract import (
    ACTIVITY_COMMIT_UNKNOWN_MESSAGE,
    ATTEMPT_DEADLINE_SECONDS,
    AssistantFailureCode,
    attempt_budget_remaining,
    bind_absolute_attempt_deadline,
    is_root_failure_code,
    reset_attempt_deadline,
    root_failure_code,
    root_failure_presentation,
    root_failure_retryable,
)
from app.services.assistant.intent import IntentVerdict, judge_intent, not_written, open_verdict_task
from app.services.assistant.model_transport import AssistantLLMError
from app.services.assistant.presentation import task_view
from app.services.assistant.task_operations import activity_commit_is_unknown
from app.services.assistant.task_state import TaskUpdate, apply_task_update, load_authority, load_draft, load_waiting
from app.services.assistant.turns import (
    AssistantRequestConflict,
    AssistantStateConflict,
    accept_create,
    accept_submit,
    schedule_turn,
)

logger = get_logger(__name__)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.assistant import AssistantTask
    from app.models.assistant_conversation import AssistantConversation, AssistantConversationEntry
    from app.services.assistant.contracts import TaskWaiting


class RootClassifier(Protocol):
    async def classify(
        self,
        db: Session,
        *,
        team_id: int,
        text: str,
        tasks: list[dict[str, object]],
        focused_task_public_id: str | None,
        recent_messages: list[dict[str, str]],
    ) -> ConversationDecision: ...



CORRECTION_UNCLEAR_MESSAGE = not_written("没听明白要改哪一项。请说明要修改的内容，例如“日期是周三不是周二”")


def _stored_links(raw: object) -> list[ConversationLink]:
    return [ConversationLink.model_validate(item) for item in raw[:4]] if isinstance(raw, list) else []


class ConversationService:
    def __init__(self, classifier: RootClassifier | None = None) -> None:
        self.classifier = classifier or ConversationRootClassifier()

    def open(self, db: Session, *, team_id: int, user_id: int) -> ConversationView:
        conversation, created = crud.open_conversation(db, team_id=team_id, user_id=user_id)
        if created:
            crud.bootstrap_active(db, conversation)
        return self.read(db, team_id=team_id, user_id=user_id)

    def read(self, db: Session, *, team_id: int, user_id: int, before: int | None = None) -> ConversationView:
        conversation = crud.owned_conversation(db, team_id=team_id, user_id=user_id)
        if conversation is None:
            raise crud.ConversationConflict("请先打开销售助手会话。")
        db.refresh(conversation)
        rows, older = crud.page(db, conversation, before=before)
        messages = []
        for row in rows:
            try:
                messages.extend(self._messages(db, conversation, row))
            except SQLAlchemyError:
                raise
            except Exception as exc:
                if is_database_schema_mismatch(exc):
                    raise
                logger.warning(
                    "assistant history entry projection failed: entry=%s error_type=%s",
                    row.public_id,
                    type(exc).__name__,
                )
                messages.extend(self._unavailable_messages(row))
        focused = crud.owned_task(db, conversation, conversation.focused_task_public_id)
        pending = (
            crud.owned_entry(db, conversation, conversation.pending_choice_id)
            if conversation.pending_choice_id
            else None
        )
        focused_view = task_view(focused, db) if focused else None
        pending_choice = (
            ConversationBoundary(entry_id=pending.public_id, prompt=pending.reply_text or "是接着刚才，还是另记一件？")
            if pending
            else None
        )
        from app.services.assistant.ui_projection import finalize_assistant_ui

        finalize_assistant_ui(messages, focused_task=focused_view, pending_choice=pending_choice)
        return ConversationView(
            public_id=conversation.public_id,
            version=conversation.version,
            focused_task=focused_view,
            pending_choice=pending_choice,
            messages=messages,
            older_cursor=older,
            has_pending_request=conversation.busy_entry_id is not None,
        )

    def _messages(
        self, db: Session, conversation: AssistantConversation, row: AssistantConversationEntry
    ) -> list[ConversationMessage]:
        at = row.created_time.isoformat()
        result = [ConversationMessage(id=f"{row.public_id}:user", role="user", text=row.user_text, at=at)]
        owned = crud.owned_task(db, conversation, row.task_public_id)
        if row.command_json.get("operation") == "legacy" and owned:
            result.extend(self._legacy_messages(db, conversation, row, owned))
        if row.reply_text:
            try:
                snapshot = AssistantTaskView.model_validate(row.task_snapshot_json) if row.task_snapshot_json else None
            except ValidationError:
                snapshot = None
            root_failure = is_root_failure_code(row.error_code)
            result.append(
                ConversationMessage(
                    id=f"{row.public_id}:reply",
                    role="assistant",
                    text=row.reply_text,
                    at=at,
                    task=snapshot,
                    links=_stored_links(row.command_json.get("links")),
                    boundary=ConversationBoundary(entry_id=row.public_id, prompt=row.reply_text)
                    if row.state == "CHOICE"
                    else None,
                    outcome="failure" if root_failure else None,
                    error_code=row.error_code if root_failure else None,
                    retryable=bool(row.error_retryable) if root_failure else None,
                )
            )
        next_id = row.turn_public_id
        seen: set[str] = set()
        while owned and next_id and next_id not in seen and len(seen) < 50:
            seen.add(next_id)
            turn = crud.owned_turn(db, conversation, owned, next_id)
            if turn is None:
                break
            next_id = None
            for event in crud.turn_events(db, turn):
                data = event.data_json
                if event.event not in {"waiting", "error"}:
                    continue
                try:
                    snapshot = AssistantTaskView.model_validate(data["task"]) if event.event == "waiting" else None
                    if snapshot and snapshot.public_id != owned.public_id:
                        raise ValueError("snapshot belongs to another task")
                    message = data.get("message")
                    if not isinstance(message, str) or not message:
                        raise ValueError("missing result message")
                    error_code = data.get("code") if event.event == "error" else None
                    retryable = data.get("retryable") if event.event == "error" else None
                    card = data.get("card")
                    is_activity = (
                        snapshot is not None
                        and row.command_json.get("waiting_field") == "activity_write"
                        and any(r.kind == "customer_activity" for r in snapshot.committed)
                        and turn.input_json.get("kind") == "confirm"
                        and turn.input_json.get("choice") == "confirm"
                    )
                    proposal_receipt = (
                        AcceptedProposalReceipt.model_validate(data["proposal_receipt"])
                        if "proposal_receipt" in data else None
                    )
                    entity_receipt = (
                        EntityCreateReceipt.model_validate(data["entity_receipt"])
                        if "entity_receipt" in data else None
                    )
                    result.append(
                        ConversationMessage(
                            id=f"{row.public_id}:{turn.public_id}:{event.seq}",
                            role="assistant",
                            text=message,
                            at=event.created_time.isoformat(),
                            task=snapshot,
                            outcome="failure"
                            if event.event == "error"
                            else "activity_written"
                            if is_activity
                            else "follow_up_disposition"
                            if card == "follow_up_disposition"
                            else "proposal_unavailable"
                            if snapshot and snapshot.proposal_outcome is not None and snapshot.waiting is None
                            else "task_completed"
                            if snapshot and snapshot.status == "COMPLETED" and snapshot.waiting is None
                            and proposal_receipt is None
                            and entity_receipt is None
                            else None,
                            error_code=error_code if isinstance(error_code, str) else None,
                            retryable=retryable if isinstance(retryable, bool) else None,
                            projection=self._structured_projection(snapshot, card=card, is_activity=is_activity),
                            proposal_receipt=proposal_receipt,
                            entity_receipt=entity_receipt,
                        )
                    )
                    followup = data.get("next_turn_id")
                    next_id = followup if isinstance(followup, str) else None
                except (ValidationError, ValueError, KeyError):
                    result.append(
                        ConversationMessage(
                            id=f"{row.public_id}:{turn.public_id}:{event.seq}:invalid",
                            role="assistant",
                            text="这条历史结果暂时无法显示",
                            at=event.created_time.isoformat(),
                            outcome="failure",
                            error_code="INTERNAL_ERROR",
                            retryable=False,
                        )
                    )
        return result

    @staticmethod
    def _activity_projection(snapshot: AssistantTaskView | None) -> ConversationProjection | None:
        if snapshot is None:
            return None
        activity_id = next(
            (receipt.public_id for receipt in snapshot.committed if receipt.kind == "customer_activity"),
            None,
        )
        return ConversationProjection(activity_public_id=activity_id) if activity_id else None

    @classmethod
    def _structured_projection(
        cls, snapshot: AssistantTaskView | None, *, card: object, is_activity: bool
    ) -> ConversationProjection | None:
        """Project only durable activity receipts and minted disposition batches."""
        activity = cls._activity_projection(snapshot) if is_activity else None
        disposition = None
        if snapshot is not None and card == "follow_up_disposition":
            payload = snapshot.follow_up_disposition
            if isinstance(payload, dict):
                batch_id = payload.get("batch_id")
                items = payload.get("items")
                if isinstance(batch_id, str) and batch_id.strip() and isinstance(items, list):
                    item_ids = [
                        item["item_id"]
                        for item in items
                        if isinstance(item, dict)
                        and isinstance(item.get("item_id"), str)
                        and item["item_id"].strip()
                    ]
                    role = (
                        "FINAL"
                        if payload.get("status") == "DONE"
                        else "CURRENT"
                        if snapshot.status == "ACTIVE"
                        and snapshot.waiting is not None
                        and snapshot.waiting.type == "FOLLOW_UP_DISPOSITION"
                        else "NONE"
                    )
                    disposition = ConversationDispositionProjection(
                        task_public_id=snapshot.public_id,
                        batch_id=batch_id,
                        item_ids=item_ids,
                        card_role=role,
                        version=snapshot.version,
                    )
        if activity is None and disposition is None:
            return None
        return ConversationProjection(
            activity_public_id=activity.activity_public_id if activity is not None else None,
            disposition=disposition,
        )

    @staticmethod
    def _unavailable_messages(row: AssistantConversationEntry) -> list[ConversationMessage]:
        at = row.created_time.isoformat()
        return [
            ConversationMessage(id=f"{row.public_id}:user", role="user", text=row.user_text, at=at),
            ConversationMessage(
                id=f"{row.public_id}:unavailable",
                role="assistant",
                text="这条历史结果暂时无法显示",
                at=at,
                outcome="failure",
                error_code="INTERNAL_ERROR",
                retryable=False,
            ),
        ]

    def _legacy_messages(
        self, db: Session, conversation: AssistantConversation, row: AssistantConversationEntry, task: AssistantTask
    ) -> list[ConversationMessage]:
        from app.services.assistant.history import legacy_messages

        messages = legacy_messages(task, crud.legacy_actions(db, conversation, task), row.public_id)
        if row.reply_text and row.task_snapshot_json:
            try:
                snapshot = AssistantTaskView.model_validate(row.task_snapshot_json)
                current = snapshot.waiting
                messages = [
                    message
                    for message in messages
                    if not (
                        current
                        and message.task
                        and message.task.waiting
                        and message.task.waiting.question_id == current.question_id
                        and message.task.waiting.confirmation_payload == current.confirmation_payload
                    )
                ]
            except ValidationError:
                pass  # The independently valid immutable actions remain readable.
        return messages

    def _conversation(self, db: Session, team_id: int, user_id: int) -> AssistantConversation:
        result = crud.owned_conversation(db, team_id=team_id, user_id=user_id)
        if result is None:
            raise crud.ConversationConflict("请先打开销售助手会话。")
        db.refresh(result)
        return result

    def _reply(
        self, db: Session, conversation: AssistantConversation, entry: AssistantConversationEntry
    ) -> ConversationReply:
        task = crud.owned_task(db, conversation, entry.task_public_id)
        submission = None
        if task and entry.turn_public_id:
            turn = crud.owned_turn(db, conversation, task, entry.turn_public_id)
            if turn:
                payload = SubmitInputRequest.model_validate(
                    {
                        **{key: value for key, value in turn.input_json.items() if key in {
                            "kind", "text", "choice", "values", "form_revision", "choices", "suppress_week", "reason"
                        }},
                        "client_request_id": f"conv-turn-{entry.public_id}",
                        "action_id": entry.command_json.get("action_id"),
                        "expected_version": entry.command_json.get("task_version"),
                    }
                )
                submission = PreparedSubmission(task_public_id=task.public_id, turn_id=turn.public_id, input=payload)
                if turn.status in {"PENDING", "RUNNING"}:
                    schedule_turn(turn.id)
        return ConversationReply(
            conversation=self.read(db, team_id=conversation.team_id, user_id=conversation.user_id),
            submission=submission,
        )

    def _finish_message(
        self,
        db: Session,
        conversation: AssistantConversation,
        entry: AssistantConversationEntry,
        message: str,
        task: AssistantTask | None = None,
        *,
        lease_version: int,
        links: tuple[ConversationLink, ...] = (),
    ) -> ConversationReply:
        if task is not None:
            entry.task_public_id = task.public_id
        entry.reply_text = message
        entry.state = "READY"
        if links:
            # Stored with the text it belongs to, so history projects the same links.
            entry.command_json = {**entry.command_json, "links": [link.model_dump(mode="json") for link in links]}
        entry.task_snapshot_json = task_view(task, db).model_dump(mode="json") if task else None
        crud.save(
            db, conversation, entry, finish=True, focus=task.public_id if task else None, lease_version=lease_version
        )
        return self._reply(db, conversation, entry)

    async def submit_text(
        self, db: Session, *, team_id: int, user_id: int, request: ConversationTextRequest
    ) -> ConversationReply:
        conversation = self._conversation(db, team_id, user_id)
        raw = request.text.strip()
        if not raw:
            raise crud.ConversationConflict("请输入这次客户沟通的内容。")
        entry, execute, lease_version = crud.claim(
            db,
            conversation,
            key=request.client_request_id,
            payload={"operation": "text", "text": raw},
            text=raw,
            expected_version=request.expected_version,
        )
        if not execute:
            return self._reply(db, conversation, entry)
        return await self._process_root_entry(db, conversation, entry, lease_version=lease_version)

    async def retry_entry(
        self, db: Session, *, team_id: int, user_id: int, entry_id: str, expected_version: int
    ) -> ConversationReply:
        conversation = self._conversation(db, team_id, user_id)
        entry = crud.owned_entry(db, conversation, entry_id)
        if entry is None:
            raise crud.ConversationConflict("会话状态已变化，请刷新后重试。")
        lease_version = crud.claim_root_retry(db, conversation, entry, expected_version=expected_version)
        return await self._process_root_entry(db, conversation, entry, lease_version=lease_version)

    async def _process_root_entry(
        self,
        db: Session,
        conversation: AssistantConversation,
        entry: AssistantConversationEntry,
        *,
        lease_version: int,
    ) -> ConversationReply:
        stored = entry.command_json.get("root_deadline")
        deadline = (
            datetime.fromisoformat(stored) if isinstance(stored, str)
            else entry.created_time + timedelta(seconds=ATTEMPT_DEADLINE_SECONDS)
        )
        if not isinstance(stored, str):
            entry.command_json = {**entry.command_json, "root_deadline": deadline.isoformat()}
        token = bind_absolute_attempt_deadline(deadline)
        try:
            return await self._process_root_attempt(db, conversation, entry, lease_version=lease_version)
        finally:
            reset_attempt_deadline(token)

    async def _process_root_attempt(
        self,
        db: Session,
        conversation: AssistantConversation,
        entry: AssistantConversationEntry,
        *,
        lease_version: int,
    ) -> ConversationReply:
        if entry.state == "ROUTING":
            remaining = attempt_budget_remaining()
            if remaining is not None and remaining <= 0:
                return self._finish_root_failure(
                    db, conversation, entry,
                    AssistantLLMError("模型服务响应超时", code=AssistantFailureCode.UPSTREAM_TIMEOUT),
                    lease_version=lease_version,
                )
            tasks = crud.candidates(db, conversation)
            recent = self.read(db, team_id=conversation.team_id, user_id=conversation.user_id).messages[-12:]
            recent_messages = [{"role": message.role, "text": message.text[:2000]} for message in recent]
            try:
                decision = await self._classify_root(
                    db,
                    conversation,
                    entry,
                    lease_version=lease_version,
                    text=entry.user_text,
                    tasks=tasks,
                    recent_messages=recent_messages,
                )
                plan = decision.semantic_plan
                if (
                    decision.task_relation == "CONTINUE_TASK"
                    and decision.boundary == "CONTINUE"
                    and decision.target_task_public_id is None
                    and decision.route in {"WORKFLOW", "CLARIFY"}
                    and min(decision.confidence, plan.confidence) >= 0.8
                    and plan.speech_act == "PROVIDE_SUPPLEMENT"
                    and plan.business_object == "CUSTOMER_ACTIVITY"
                    and plan.operation == "CREATE"
                    and plan.customer_reference
                ):
                    referenced = crud.referenced_candidates(
                        db, conversation, customer_reference=plan.customer_reference
                    )
                    if referenced:
                        tasks = referenced
                        decision = await self._classify_root(
                            db,
                            conversation,
                            entry,
                            lease_version=lease_version,
                            text=entry.user_text,
                            tasks=tasks,
                            recent_messages=recent_messages,
                        )
            except crud.ConversationConflict:
                raise
            except AssistantLLMError as exc:
                return self._finish_root_failure(db, conversation, entry, exc, lease_version=lease_version)
            except Exception as exc:
                return self._finish_root_failure(
                    db,
                    conversation,
                    entry,
                    AssistantLLMError("处理失败", code=AssistantFailureCode.INTERNAL_ERROR, cause=exc),
                    lease_version=lease_version,
                )
            entry.decision_json = decision.model_dump(mode="json")
            entry.command_json = {**entry.command_json, "route_candidate_ids": [task.public_id for task in tasks]}
            entry.state = "ROUTED"
            crud.save(db, conversation, entry, lease_version=lease_version)
        return self._route(db, conversation, entry, lease_version=lease_version)

    async def _classify_root(
        self,
        db: Session,
        conversation: AssistantConversation,
        entry: AssistantConversationEntry,
        *,
        lease_version: int,
        text: str,
        tasks: list[AssistantTask],
        recent_messages: list[dict[str, str]],
    ) -> ConversationDecision:
        remaining = attempt_budget_remaining()
        if remaining is not None and remaining <= 0:
            self._close_root_stage(db, conversation, entry, ms=0, lease_version=lease_version)
            raise AssistantLLMError("模型服务响应超时", code=AssistantFailureCode.UPSTREAM_TIMEOUT)
        stored_events = entry.command_json.get("root_stages")
        events = list(stored_events) if isinstance(stored_events, list) else []
        events.append({"stage": "route", "phase": "start"})
        entry.command_json = {**entry.command_json, "root_stages": events}
        crud.save(db, conversation, entry, lease_version=lease_version)
        started = monotonic()
        try:
            decision = await self.classifier.classify(
                db,
                team_id=conversation.team_id,
                text=text,
                tasks=self._root_context(tasks),
                focused_task_public_id=conversation.focused_task_public_id,
                recent_messages=recent_messages,
            )
            remaining = attempt_budget_remaining()
            if remaining is not None and remaining <= 0:
                raise AssistantLLMError("模型服务响应超时", code=AssistantFailureCode.UPSTREAM_TIMEOUT)
            done = {"stage": "route", "phase": "done", "ms": int((monotonic() - started) * 1000)}
            entry.command_json = {**entry.command_json, "root_stages": [*events, done]}
            crud.save(db, conversation, entry, lease_version=lease_version)
            return decision
        except crud.ConversationConflict:
            raise
        except AssistantLLMError:
            self._close_root_stage(
                db, conversation, entry, ms=int((monotonic() - started) * 1000), lease_version=lease_version,
            )
            raise
        except Exception as exc:
            self._close_root_stage(
                db, conversation, entry, ms=int((monotonic() - started) * 1000), lease_version=lease_version,
            )
            raise AssistantLLMError("处理失败", code=AssistantFailureCode.INTERNAL_ERROR, cause=exc) from exc

    @staticmethod
    def _close_root_stage(
        db: Session,
        conversation: AssistantConversation,
        entry: AssistantConversationEntry,
        *,
        ms: int,
        lease_version: int,
    ) -> None:
        """Record the failed route stage so a retry replays why the attempt stopped."""

        events = entry.command_json.get("root_stages")
        stored = list(events) if isinstance(events, list) else []
        if stored and stored[-1].get("phase") == "failed":
            return
        entry.command_json = {
            **entry.command_json,
            "root_stages": [*stored, {"stage": "route", "phase": "failed", "ms": ms}],
        }
        crud.save(db, conversation, entry, lease_version=lease_version)

    def _finish_root_failure(
        self,
        db: Session,
        conversation: AssistantConversation,
        entry: AssistantConversationEntry,
        exc: AssistantLLMError,
        *,
        lease_version: int,
    ) -> ConversationReply:
        code = root_failure_code(exc.code)
        logger.warning(
            "assistant root model failure: entry=%s code=%s error_type=%s",
            entry.public_id,
            code.value,
            type(exc.cause).__name__ if exc.cause is not None else type(exc).__name__,
        )
        entry.reply_text = root_failure_presentation(code).message
        entry.error_code = code.value
        entry.error_retryable = root_failure_retryable(code)
        entry.state = "READY"
        crud.save(db, conversation, entry, finish=True, lease_version=lease_version)
        return self._reply(db, conversation, entry)

    @staticmethod
    def _root_context(tasks: list[AssistantTask]) -> list[dict[str, object]]:
        context: list[dict[str, object]] = []
        for task in tasks:
            draft = load_draft(task)
            wait = load_waiting(task)
            context.append(
                {
                    "public_id": task.public_id,
                    "goal": task.goal[:2000],
                    "customer": draft.customer.value,
                    "status": task.status,
                    "activity_written": any(r.get("kind") == "customer_activity" for r in task.committed_json or []),
                    "waiting": wait.model_dump(mode="json", include={"type", "field", "prompt"}) if wait else None,
                }
            )
        return context

    def _route(
        self, db: Session, conversation: AssistantConversation, entry: AssistantConversationEntry, *, lease_version: int
    ) -> ConversationReply:
        decision = ConversationDecision.model_validate(entry.decision_json)
        if entry.task_public_id and isinstance(entry.command_json.get("prepared_input"), dict):
            task = crud.owned_task(db, conversation, entry.task_public_id)
            if task is None:
                return self._finish_message(
                    db, conversation, entry, not_written("原沟通已不可用"), lease_version=lease_version
                )
            return self._accept(
                db,
                conversation,
                entry,
                task,
                SubmitInputRequest.model_validate(entry.command_json["prepared_input"]),
                lease_version=lease_version,
            )
        plan = decision.semantic_plan
        supplemented = self._route_entity_text(db, conversation, entry, decision, lease_version=lease_version)
        if supplemented is not None:
            return supplemented
        verdict = judge_intent(plan, decision.confidence)
        if verdict.route == "refuse":
            return self._finish_message(
                db, conversation, entry, verdict.message, lease_version=lease_version, links=verdict.links
            )
        if verdict.route in {"entity", "intent_question"}:
            return self._create_entity_task(db, conversation, entry, verdict, lease_version=lease_version)
        target = crud.owned_task(db, conversation, decision.target_task_public_id)
        supplied_ids = entry.command_json.get("route_candidate_ids")
        if plan.speech_act == "CORRECT":
            from app.services.assistant.activity_edit import EDITABLE_ACTIVITY_FIELDS

            correction = decision.correction
            if target is not None and activity_commit_is_unknown(target):
                return self._finish_message(
                    db, conversation, entry, ACTIVITY_COMMIT_UNKNOWN_MESSAGE, target, lease_version=lease_version,
                )
            waiting = load_waiting(target) if target else None
            if (
                target is None or target.status != "ACTIVE" or target.active_turn_id is not None
                or not isinstance(supplied_ids, list) or target.public_id not in supplied_ids
                or decision.boundary != "CONTINUE" or decision.task_relation != "CONTINUE_TASK"
                or waiting is None or waiting.type != "CONFIRMATION" or waiting.field != "activity_write"
                or any(r.get("kind") == "customer_activity" for r in target.committed_json or [])
            ):
                return self._finish_message(
                    db, conversation, entry, not_written("这项不能在这里修改"), lease_version=lease_version,
                )
            if decision.route == "CLARIFY" or correction is None:
                # "Not sure what to change" is not a refusal: keep the card and ask once.
                return self._finish_message(
                    db, conversation, entry, CORRECTION_UNCLEAR_MESSAGE, target, lease_version=lease_version,
                )
            if not correction.quote.strip() or correction.quote not in entry.user_text:
                return self._finish_message(
                    db, conversation, entry, CORRECTION_UNCLEAR_MESSAGE, target, lease_version=lease_version,
                )
            if correction.field not in EDITABLE_ACTIVITY_FIELDS:
                return self._finish_message(
                    db, conversation, entry, not_written("这项不能在这里修改"), target, lease_version=lease_version,
                )
            entry.command_json = {**entry.command_json, "correction": correction.model_dump(mode="json")}
            return self._accept(db, conversation, entry, target, SubmitInputRequest(
                kind="text", text=entry.user_text, client_request_id=f"conv-turn-{entry.public_id}",
                action_id=waiting.action_id, expected_version=waiting.expected_version,
            ), lease_version=lease_version)
        if decision.boundary != "NEW" and (
            target is None or not isinstance(supplied_ids, list) or decision.target_task_public_id not in supplied_ids
        ):
            return self._finish_message(
                db, conversation, entry, not_written("请说明要接回哪次客户沟通"), lease_version=lease_version
            )
        if decision.boundary == "AMBIGUOUS" and target:
            name = load_draft(target).customer.value
            entry.reply_text = f"这句是接着刚才的{name}，还是另记一件？" if name else "这句是接着刚才，还是另记一件？"
            entry.state = "CHOICE"
            crud.save(db, conversation, entry, finish=True, pending_choice=entry.public_id, lease_version=lease_version)
            return self._reply(db, conversation, entry)
        if decision.route != "WORKFLOW":
            return self._finish_message(
                db,
                conversation,
                entry,
                not_written("请补充这次沟通的客户和要记录的内容"),
                lease_version=lease_version,
            )
        return self._dispatch(
            db,
            conversation,
            entry,
            target=target if decision.boundary == "CONTINUE" else None,
            lease_version=lease_version,
        )

    def _route_entity_text(
        self, db: Session, conversation: AssistantConversation, entry: AssistantConversationEntry,
        decision: ConversationDecision, *, lease_version: int,
    ) -> ConversationReply | None:
        """D19: the open entity form takes the text first; else exactly one parked draft may resume."""

        from app.services.assistant.entity_tasks import is_defer_text
        from app.services.assistant.intent import ENTITY_LABELS, ENTITY_TASK_KINDS

        plan = decision.semantic_plan
        text = entry.user_text
        supplementing = plan.speech_act in {"PROVIDE_SUPPLEMENT", "CORRECT"}
        focused = crud.owned_task(db, conversation, decision.target_task_public_id) or crud.owned_task(
            db, conversation, conversation.focused_task_public_id
        )
        waiting = load_waiting(focused) if focused is not None else None
        if (
            focused is not None and waiting is not None and focused.status == "ACTIVE"
            and focused.task_kind != "customer_activity" and focused.active_turn_id is None
            and waiting.type == "ENTITY_FORM" and (supplementing or is_defer_text(text))
        ):
            return self._accept_text(db, conversation, entry, focused, waiting, lease_version=lease_version)
        if plan.speech_act != "PROVIDE_SUPPLEMENT" or (
            focused is not None and focused.status == "ACTIVE" and focused.task_kind == "customer_activity"
        ):
            return None
        drafts = crud.deferred_entity_tasks(db, conversation)
        kind = ENTITY_TASK_KINDS.get(plan.business_object)
        if kind is not None:
            drafts = [task for task in drafts if task.task_kind == kind]
        named = [task for task in drafts if (name := _draft_customer(task)) and name in text]
        drafts = named or drafts
        if not drafts:
            return None
        if len(drafts) > 1:
            listed = "、".join(
                f"{_draft_customer(task) or '未定客户'}的{ENTITY_LABELS[task.task_kind]}" for task in drafts[:5]
            )
            return self._finish_message(db, conversation, entry, not_written(
                f"待补充里有几份草稿：{listed}。要补到哪一份？请先在「待补充」里打开它"
            ), lease_version=lease_version)
        task = drafts[0]
        parked = load_waiting(task)
        if task.active_turn_id is not None or parked is None:
            return None
        return self._accept_text(db, conversation, entry, task, parked, lease_version=lease_version)

    def _accept_text(
        self, db: Session, conversation: AssistantConversation, entry: AssistantConversationEntry,
        task: AssistantTask, waiting: TaskWaiting, *, lease_version: int,
    ) -> ConversationReply:
        return self._accept(db, conversation, entry, task, SubmitInputRequest(
            kind="text", text=entry.user_text, client_request_id=f"conv-turn-{entry.public_id}",
            action_id=waiting.action_id, expected_version=waiting.expected_version,
        ), lease_version=lease_version)

    async def choose(
        self, db: Session, *, team_id: int, user_id: int, request: ConversationChoiceRequest
    ) -> ConversationReply:
        conversation = self._conversation(db, team_id, user_id)
        previous = crud.request_entry(db, conversation, request.client_request_id)
        source = crud.owned_entry(db, conversation, request.entry_id)
        if source is None or (
            previous is None and (source.public_id != conversation.pending_choice_id or source.state != "CHOICE")
        ):
            raise crud.ConversationConflict("这个选择已过期，请同步最新会话。")
        choice_payload: dict[str, object] = {
            "operation": "choice",
            "entry_id": request.entry_id,
            "choice": request.choice,
        }
        entry, execute, lease_version = crud.claim(
            db,
            conversation,
            key=request.client_request_id,
            payload=choice_payload,
            text="接着刚才"
            if request.choice == "CONTINUE"
            else "算了，不记了"
            if request.choice == "CANCEL"
            else "另记一件",
            expected_version=request.expected_version,
            choice_id=source.public_id,
        )
        if not execute:
            return self._reply(db, conversation, entry)
        if request.choice == "CANCEL":
            return self._finish_message(
                db, conversation, entry, "当前这件已停下，之前的对话仍保留。", lease_version=lease_version
            )
        decision = ConversationDecision.model_validate(source.decision_json)
        target = crud.owned_task(db, conversation, decision.target_task_public_id)
        if request.choice == "CONTINUE" and target is None:
            return self._finish_message(
                db, conversation, entry, "原沟通状态已变化，请重新说明客户和沟通内容。", lease_version=lease_version
            )
        entry.command_json = {**entry.command_json, "text": source.user_text, "choice_payload": choice_payload}
        entry.decision_json = source.decision_json
        entry.state = "ROUTED"
        crud.save(db, conversation, entry, lease_version=lease_version)
        return self._dispatch(
            db,
            conversation,
            entry,
            target=target if request.choice == "CONTINUE" else None,
            lease_version=lease_version,
        )

    def _dispatch(
        self,
        db: Session,
        conversation: AssistantConversation,
        entry: AssistantConversationEntry,
        *,
        target: AssistantTask | None,
        lease_version: int,
    ) -> ConversationReply:
        crud.save(db, conversation, entry, lease_version=lease_version)  # lease fence before any task acceptance
        text = str(entry.command_json.get("text") or entry.user_text)
        if ConversationDecision.model_validate(entry.decision_json).resume_only:
            if target is None:
                return self._finish_message(
                    db, conversation, entry, not_written("请说明要接回哪次客户沟通"), lease_version=lease_version
                )
            waiting = load_waiting(target)
            return self._finish_message(
                db,
                conversation,
                entry,
                waiting.prompt if waiting else "已接回这次沟通；原记录保持不变，可以继续描述补充内容。",
                target,
                lease_version=lease_version,
            )
        if entry.task_public_id and isinstance(entry.command_json.get("prepared_input"), dict):
            prepared_task = crud.owned_task(db, conversation, entry.task_public_id)
            if prepared_task is None:
                return self._finish_message(
                    db, conversation, entry, not_written("原沟通已不可用"), lease_version=lease_version
                )
            return self._accept(
                db,
                conversation,
                entry,
                prepared_task,
                SubmitInputRequest.model_validate(entry.command_json["prepared_input"]),
                lease_version=lease_version,
            )
        if target is not None and activity_commit_is_unknown(target):
            return self._finish_message(
                db, conversation, entry, ACTIVITY_COMMIT_UNKNOWN_MESSAGE, target, lease_version=lease_version,
            )
        if (
            target is None
            or target.status != "ACTIVE"
            or target.task_kind != "customer_activity"
            or any(r.get("kind") == "customer_activity" for r in target.committed_json or [])
        ):
            source = target
            target = accept_create(
                db,
                team_id=conversation.team_id,
                user_id=conversation.user_id,
                key=f"conv-create-{entry.public_id}",
                goal=text,
            )
            if source and target.version == 0:
                authority = load_authority(source)
                draft = load_draft(source)
                if authority.customer_public_id and draft.customer.value:
                    from app.services.assistant.customer_resolution import resolve_customer_candidates_for_assistant

                    resolved = resolve_customer_candidates_for_assistant(
                        db,
                        team_id=conversation.team_id,
                        user_id=conversation.user_id,
                        customer_name=draft.customer.value,
                    )
                    if resolved.customer and resolved.customer.public_id == authority.customer_public_id:
                        target = apply_task_update(
                            db,
                            target,
                            TaskUpdate(
                                draft=TaskDraft(
                                    customer=DraftField(status="ACCEPTED", value=str(resolved.customer.account_name))
                                ),
                                authority=TaskAuthority(customer_public_id=str(resolved.customer.public_id)),
                                action_actor="SYSTEM",
                                action_name="inherit_conversation_customer",
                            ),
                        ).task
                        db.commit()
        waiting = load_waiting(target)
        if target.active_turn_id is not None:
            return self._finish_message(
                db, conversation, entry, "这次沟通仍在处理中，请同步后继续。", target, lease_version=lease_version
            )
        decision = ConversationDecision.model_validate(entry.decision_json)
        from app.services.assistant.temporal_evidence import (
            is_temporal_choice_answer,
            is_temporal_supplement,
            temporal_supplement_target,
        )

        temporal_field_answer = (
            waiting is not None
            and (
                decision.field_answer
                or is_temporal_supplement(text)
                or is_temporal_choice_answer(load_draft(target), text)
            )
            and waiting.type == "FIELD"
            and (
                waiting.temporal_target is not None
                or waiting.field == "temporal_choice"
                or (waiting.field == "next_follow_time" and "temporal_evidence" in load_draft(target).content_json)
            )
        )
        temporal_correction = bool(
            waiting is not None
            and waiting.type == "CONFIRMATION"
            and waiting.field == "activity_write"
            and decision.semantic_plan.speech_act == "PROVIDE_SUPPLEMENT"
            and is_temporal_supplement(text)
            and temporal_supplement_target(load_draft(target)) is not None
        )
        if (
            waiting is not None
            and not temporal_correction
            and not temporal_field_answer
            and not (waiting.type == "FIELD" and decision.field_answer)
        ):
            if decision.semantic_plan.speech_act == "PROVIDE_SUPPLEMENT" and (
                waiting.type in {"FIELD", "OBJECT_SELECTION", "ACTIVITY_KIND"}
                or (waiting.type == "CONFIRMATION" and waiting.field == "activity_write")
            ):
                target = apply_task_update(
                    db,
                    target,
                    TaskUpdate(
                        require_no_active_turn=True,
                        clear_waiting=True,
                        clear_frozen_activity_command=True,
                        action_actor="USER",
                        action_name="supplement_activity_draft",
                    ),
                ).task
                db.commit()
                waiting = None
            else:
                return self._finish_message(
                    db, conversation, entry, waiting.prompt, target, lease_version=lease_version
                )
        payload = SubmitInputRequest(
            kind="text" if temporal_correction else "submit_field" if waiting else "text",
            text=text,
            client_request_id=f"conv-turn-{entry.public_id}",
            action_id=waiting.action_id if waiting else None,
            expected_version=waiting.expected_version if waiting else None,
        )
        return self._accept(db, conversation, entry, target, payload, lease_version=lease_version)

    def _create_entity_task(
        self,
        db: Session,
        conversation: AssistantConversation,
        entry: AssistantConversationEntry,
        verdict: IntentVerdict,
        *,
        lease_version: int,
    ) -> ConversationReply:
        """One record = one task; an unsure create first asks entity-vs-activity on that task."""

        task = open_verdict_task(
            db,
            team_id=conversation.team_id,
            user_id=conversation.user_id,
            key=f"conv-create-{entry.public_id}",
            goal=entry.user_text,
            verdict=verdict,
        )
        if verdict.route == "intent_question":
            waiting = load_waiting(task)
            prompt = waiting.prompt if waiting is not None else "已按你的选择继续处理。"
            return self._finish_message(db, conversation, entry, prompt, task, lease_version=lease_version)
        return self._accept(
            db,
            conversation,
            entry,
            task,
            SubmitInputRequest(kind="text", text=entry.user_text, client_request_id=f"conv-turn-{entry.public_id}"),
            lease_version=lease_version,
        )

    def _accept(
        self,
        db: Session,
        conversation: AssistantConversation,
        entry: AssistantConversationEntry,
        task: AssistantTask,
        payload: SubmitInputRequest,
        *,
        lease_version: int,
    ) -> ConversationReply:
        entry.task_public_id = task.public_id
        entry.command_json = {
            **entry.command_json,
            "action_id": payload.action_id,
            "task_version": payload.expected_version,
            "prepared_input": payload.model_dump(mode="json"),
        }
        crud.save(db, conversation, entry, focus=task.public_id, lease_version=lease_version)
        try:
            turn, _ = accept_submit(
                db,
                task=task,
                key=payload.client_request_id,
                input_data=payload.turn_input(),
                action_id=payload.action_id,
                expected_version=payload.expected_version,
                prepared_metadata={
                    key: entry.command_json[key]
                    for key in ("correction", "root_deadline", "root_stages")
                    if key in entry.command_json
                },
            )
        except (AssistantRequestConflict, AssistantStateConflict):
            db.refresh(task)
            return self._finish_message(
                db,
                conversation,
                entry,
                "这张卡片状态已变化，请按当前提示继续；这次没有新增写入。",
                task,
                lease_version=lease_version,
            )
        entry.turn_public_id = turn.public_id
        entry.state = "READY"
        crud.save(db, conversation, entry, finish=True, focus=task.public_id, lease_version=lease_version)
        return self._reply(db, conversation, entry)

    async def command(
        self, db: Session, *, team_id: int, user_id: int, request: ConversationCommandRequest
    ) -> ConversationReply:
        conversation = self._conversation(db, team_id, user_id)
        payload = request.input
        if payload.kind == "text":
            raise crud.ConversationConflict("普通文本必须先判断这次沟通的归属。")
        previous = crud.request_entry(db, conversation, payload.client_request_id)
        normalized = {
            "operation": "command",
            "task_public_id": request.task_public_id,
            **payload.model_dump(
                mode="json", exclude={"values", "form_revision", "choices", "suppress_week", "reason"},
            ),
            **{key: value for key, value in payload.turn_input().items() if key not in {"kind", "text", "choice"}},
        }
        if previous is None and request.task_public_id != conversation.focused_task_public_id:
            raise crud.ConversationConflict("这张卡片不是当前沟通，请先接回对应沟通。")
        task = crud.owned_task(db, conversation, request.task_public_id)
        if task is None:
            raise crud.ConversationConflict("这次沟通不存在。")
        from app.services.assistant.history import command_label

        label = command_label(payload, load_waiting(task))
        entry, execute, lease_version = crud.claim(
            db,
            conversation,
            key=payload.client_request_id,
            payload=normalized,
            text=label,
            expected_version=request.expected_version,
        )
        if not execute:
            return self._reply(db, conversation, entry)
        if "waiting_field" not in entry.command_json:
            current_wait = load_waiting(task)
            entry.command_json = {**entry.command_json, "waiting_field": current_wait.field if current_wait else None}
        prepared = payload.model_copy(update={"client_request_id": f"conv-turn-{entry.public_id}"})
        return self._accept(db, conversation, entry, task, prepared, lease_version=lease_version)

    async def resume(self, db: Session, *, team_id: int, user_id: int) -> ConversationReply:
        """Resume only this owner's persisted request, using its original idempotency key."""
        conversation = self._conversation(db, team_id, user_id)
        entry = crud.owned_entry(db, conversation, conversation.busy_entry_id) if conversation.busy_entry_id else None
        if entry is None:
            return ConversationReply(conversation=self.read(db, team_id=team_id, user_id=user_id))
        stored = entry.command_json
        common = {"client_request_id": entry.client_request_id, "expected_version": conversation.version}
        if stored.get("operation") == "text":
            return await self.submit_text(
                db,
                team_id=team_id,
                user_id=user_id,
                request=ConversationTextRequest.model_validate({**common, "text": entry.user_text}),
            )
        if stored.get("operation") == "choice":
            return await self.choose(
                db,
                team_id=team_id,
                user_id=user_id,
                request=ConversationChoiceRequest.model_validate(
                    {**common, "entry_id": stored.get("entry_id"), "choice": stored.get("choice")}
                ),
            )
        if stored.get("operation") == "command":
            payload = {key: value for key, value in stored.items() if key in SubmitInputRequest.model_fields}
            return await self.command(
                db,
                team_id=team_id,
                user_id=user_id,
                request=ConversationCommandRequest.model_validate(
                    {
                        "expected_version": conversation.version,
                        "task_public_id": stored.get("task_public_id"),
                        "input": payload,
                    }
                ),
            )
        if stored.get("operation") == "kind":
            return self.change_kind(
                db,
                team_id=team_id,
                user_id=user_id,
                request=ConversationKindRequest.model_validate(
                    {key: value for key, value in stored.items() if key != "operation"}
                ),
            )
        raise crud.ConversationConflict("上次发送暂时无法恢复，请保留当前对话并联系管理员。")

    def change_kind(
        self, db: Session, *, team_id: int, user_id: int, request: ConversationKindRequest
    ) -> ConversationReply:
        from app.services.assistant.history import KIND_LABELS
        from app.services.assistant.task_operations import reset_activity_kind
        from app.services.assistant.task_state import InvalidTaskTransitionError, TaskStateConflictError

        conversation = self._conversation(db, team_id, user_id)
        previous = crud.request_entry(db, conversation, request.client_request_id)
        if previous is None and conversation.focused_task_public_id != request.task_public_id:
            raise crud.ConversationConflict("这张卡片不是当前沟通，请先接回对应沟通。")
        task = crud.owned_task(db, conversation, request.task_public_id)
        if task is None:
            raise crud.ConversationConflict("这次沟通不存在。")
        entry, execute, lease_version = crud.claim(
            db,
            conversation,
            key=request.client_request_id,
            payload={"operation": "kind", **request.model_dump(mode="json")},
            text=f"改为{KIND_LABELS[request.kind]}",
            expected_version=request.expected_version,
        )
        if not execute:
            return self._reply(db, conversation, entry)
        try:
            if task.version != request.task_version:
                raise TaskStateConflictError("卡片版本已变化")
            task = reset_activity_kind(db, task, request.kind)
        except (TaskStateConflictError, InvalidTaskTransitionError):
            db.rollback()
            db.refresh(task)
            return self._finish_message(
                db,
                conversation,
                entry,
                "这张卡片状态已变化，请按当前提示继续；这次没有新增写入。",
                task,
                lease_version=lease_version,
            )
        entry.task_public_id = task.public_id
        return self._finish_message(
            db,
            conversation,
            entry,
            f"已切换为{KIND_LABELS[request.kind]}，请重新描述这次沟通。",
            task,
            lease_version=lease_version,
        )


def _draft_customer(task: AssistantTask) -> str | None:
    entity = load_draft(task).entity
    return entity.customer_name if entity is not None else None
