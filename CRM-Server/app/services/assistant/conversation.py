"""Conversation orchestration over the existing task/turn/CRM atomic boundaries."""
# ruff: noqa: RUF001 -- Chinese user-facing copy uses native punctuation.

from __future__ import annotations

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
    ConversationKindRequest,
    ConversationMessage,
    ConversationReply,
    ConversationTextRequest,
    ConversationView,
    PreparedSubmission,
)
from app.services.assistant.contracts import DraftField, TaskAuthority, TaskDraft
from app.services.assistant.conversation_router import ConversationRootClassifier
from app.services.assistant.model_transport import AssistantLLMError
from app.services.assistant.presentation import task_view
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
            ConversationBoundary(
                entry_id=pending.public_id, prompt=pending.reply_text or "是接着刚才，还是另记一件？"
            )
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
            result.append(
                ConversationMessage(
                    id=f"{row.public_id}:reply",
                    role="assistant",
                    text=row.reply_text,
                    at=at,
                    task=snapshot,
                    boundary=ConversationBoundary(entry_id=row.public_id, prompt=row.reply_text)
                    if row.state == "CHOICE"
                    else None,
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
                            if snapshot
                            and row.command_json.get("waiting_field") == "activity_write"
                            and any(r.kind == "customer_activity" for r in snapshot.committed)
                            and turn.input_json.get("kind") == "confirm"
                            else None,
                            error_code=error_code if isinstance(error_code, str) else None,
                            retryable=retryable if isinstance(retryable, bool) else None,
                        )
                    )
                    followup = data.get("next_turn_id")
                    next_id = followup if isinstance(followup, str) else None
                except (ValidationError, ValueError, KeyError):
                    result.append(
                        ConversationMessage(
                            id=f"{row.public_id}:{turn.public_id}:{event.seq}:invalid",
                            role="assistant",
                            text="这条历史结果暂时无法显示，原记录仍保留。",
                            at=event.created_time.isoformat(),
                            outcome="failure",
                            error_code="INTERNAL_ERROR",
                            retryable=False,
                        )
                    )
        return result

    @staticmethod
    def _unavailable_messages(row: AssistantConversationEntry) -> list[ConversationMessage]:
        at = row.created_time.isoformat()
        return [
            ConversationMessage(id=f"{row.public_id}:user", role="user", text=row.user_text, at=at),
            ConversationMessage(
                id=f"{row.public_id}:unavailable",
                role="assistant",
                text="这条历史结果暂时无法显示，原记录仍保留。",
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
                        **{key: value for key, value in turn.input_json.items() if key in {"kind", "text", "choice"}},
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
    ) -> ConversationReply:
        if task is not None:
            entry.task_public_id = task.public_id
        entry.reply_text = message
        entry.state = "READY"
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
        if entry.state == "ROUTING":
            tasks = crud.candidates(db, conversation)
            recent = self.read(db, team_id=team_id, user_id=user_id).messages[-12:]
            try:
                decision = await self.classifier.classify(
                    db,
                    team_id=team_id,
                    text=raw,
                    tasks=self._root_context(tasks),
                    focused_task_public_id=conversation.focused_task_public_id,
                    recent_messages=[{"role": m.role, "text": m.text[:2000]} for m in recent],
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
                        decision = await self.classifier.classify(
                            db,
                            team_id=team_id,
                            text=raw,
                            tasks=self._root_context(tasks),
                            focused_task_public_id=conversation.focused_task_public_id,
                            recent_messages=[{"role": m.role, "text": m.text[:2000]} for m in recent],
                        )
            except (AssistantLLMError, ValidationError, TimeoutError, ValueError):
                return self._finish_message(
                    db,
                    conversation,
                    entry,
                    "暂时无法判断这次沟通，没有写入客户活动，请稍后重新发送。",
                    lease_version=lease_version,
                )
            entry.decision_json = decision.model_dump(mode="json")
            entry.command_json = {**entry.command_json, "route_candidate_ids": [t.public_id for t in tasks]}
            entry.state = "ROUTED"
            crud.save(db, conversation, entry, lease_version=lease_version)
        return self._route(db, conversation, entry, lease_version=lease_version)

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
                    db, conversation, entry, "原沟通已不可用，目前没有写入。", lease_version=lease_version
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
        if min(decision.confidence, plan.confidence) < 0.8:
            return self._finish_message(
                db, conversation, entry, "请说明这次客户沟通要记录什么；目前没有写入。", lease_version=lease_version
            )
        if plan.speech_act == "ASK_FACT" and plan.operation == "READ":
            return self._finish_message(
                db,
                conversation,
                entry,
                "销售助手目前只记录客户沟通，请到 AI Agent 查询；这次没有写入。",
                lease_version=lease_version,
            )
        if (
            plan.business_object != "CUSTOMER_ACTIVITY"
            or plan.operation != "CREATE"
            or plan.speech_act not in {"ASSERT_EVENT", "REQUEST_ACTION", "PROVIDE_SUPPLEMENT"}
        ):
            return self._finish_message(
                db,
                conversation,
                entry,
                "这里只记录客户沟通，这类操作请到对应业务页面处理；这次没有写入。",
                lease_version=lease_version,
            )
        target = crud.owned_task(db, conversation, decision.target_task_public_id)
        supplied_ids = entry.command_json.get("route_candidate_ids")
        if decision.boundary != "NEW" and (
            target is None or not isinstance(supplied_ids, list) or decision.target_task_public_id not in supplied_ids
        ):
            return self._finish_message(
                db, conversation, entry, "请说明要接回哪次客户沟通，目前没有写入。", lease_version=lease_version
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
                "请补充这次沟通的客户和要记录的内容，目前没有写入。",
                lease_version=lease_version,
            )
        return self._dispatch(
            db,
            conversation,
            entry,
            target=target if decision.boundary == "CONTINUE" else None,
            lease_version=lease_version,
        )

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
                    db, conversation, entry, "请说明要接回哪次客户沟通，目前没有写入。", lease_version=lease_version
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
                    db, conversation, entry, "原沟通已不可用，目前没有写入。", lease_version=lease_version
                )
            return self._accept(
                db,
                conversation,
                entry,
                prepared_task,
                SubmitInputRequest.model_validate(entry.command_json["prepared_input"]),
                lease_version=lease_version,
            )
        if (
            target is None
            or target.status != "ACTIVE"
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
        if waiting is not None and not (waiting.type == "FIELD" and decision.field_answer):
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
            kind="submit_field" if waiting else "text",
            text=text,
            client_request_id=f"conv-turn-{entry.public_id}",
            action_id=waiting.action_id if waiting else None,
            expected_version=waiting.expected_version if waiting else None,
        )
        return self._accept(db, conversation, entry, target, payload, lease_version=lease_version)

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
                input_data={"kind": payload.kind, "text": payload.text, "choice": payload.choice},
                action_id=payload.action_id,
                expected_version=payload.expected_version,
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
            **payload.model_dump(mode="json"),
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
