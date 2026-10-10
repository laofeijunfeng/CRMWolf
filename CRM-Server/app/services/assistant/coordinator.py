"""Coordinate durable intake, typed waits, frozen writes and CRM proposals."""
# ruff: noqa: RUF001

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.services.assistant.confirmation import ActivityWriter
    from app.services.assistant.intake import KindStructurer

from app.models.assistant import AssistantTask, AssistantTaskStatus, AssistantWaitingType
from app.services.assistant.action_evidence import append_source, parse_deadline, reconcile_action_evidence
from app.services.assistant.confirmation import execute_confirmation, freeze_confirmation
from app.services.assistant.contracts import DraftField, TaskAuthority, TaskWaiting
from app.services.assistant.customer_resolution import resolve_customer_candidates_for_assistant
from app.services.assistant.events import NullProgressReporter, ProgressReporter
from app.services.assistant.intake_flow import intake_step
from app.services.assistant.llm import AssistantLLMError
from app.services.assistant.task_state import (
    InvalidTaskTransitionError,
    TaskUpdate,
    apply_task_update,
    load_draft,
    load_waiting,
)
from app.utils.time import resolve_follow_up_time


class AssistantInput(BaseModel):
    """One channel-normalized user submission."""

    model_config = ConfigDict(extra="forbid")

    kind: str = Field(min_length=1, max_length=32, description="text | submit_field | confirm | cancel")
    text: str | None = Field(default=None, max_length=20000, description="text or field answer payload")
    choice: str | None = Field(default=None, max_length=64, description="enum choice payload (kind, confirm)")


class CoordinatorReply(BaseModel):
    """What the coordinator produced for one submission."""

    model_config = ConfigDict(extra="forbid")

    task_public_id: str
    status: str
    message: str = Field(min_length=1, max_length=2000)
    waiting: TaskWaiting | None = None


@dataclass(frozen=True)
class NextActionDecision:
    """Agent-LLM seam output: one action name plus candidate parameters."""

    action: str
    parameters: dict[str, object]


class NextActionChooser(Protocol):
    """Agent-LLM seam; production implementation is async."""

    async def choose(self, task: AssistantTask) -> NextActionDecision: ...


@dataclass
class CoordinatorOutcome:
    reply: CoordinatorReply
    task: AssistantTask
    start_followup: bool = False


class AssistantCoordinator:
    """Owns waiting-state routing; never extracts business fields itself."""

    def __init__(
        self,
        next_action_chooser: NextActionChooser,
        structurer: KindStructurer | None = None,
        writer: ActivityWriter | None = None,
        proposal_executor: object | None = None,
        quality_gate: object | None = None,
    ) -> None:
        self._next_action_chooser = next_action_chooser
        self._structurer = structurer
        self._writer = writer
        self._proposal_executor = proposal_executor
        self._quality_gate = quality_gate

    async def handle_task(
        self,
        db: Session,
        task: AssistantTask,
        user_input: AssistantInput,
        reporter: ProgressReporter | None = None,
    ) -> CoordinatorOutcome:
        if reporter is None:
            reporter = NullProgressReporter()
        if task.status in {"COMPLETED", "CANCELLED", "FAILED"}:
            raise InvalidTaskTransitionError(
                f"task {task.public_id} is terminal ({task.status}); no further transitions"
            )

        waiting = load_waiting(task)

        if user_input.kind == "cancel":
            return self._cancel(db, task)
        if user_input.kind == "continue_proposals":
            if waiting is not None or not any(
                item.get("kind") == "customer_activity" for item in task.committed_json or []
            ):
                raise InvalidTaskTransitionError("proposal continuation requires a committed activity")
            from app.services.assistant.proposals import offer_next_proposal

            updated, message, _ = await offer_next_proposal(db, task)
            return CoordinatorOutcome(
                CoordinatorReply(
                    task_public_id=updated.public_id,
                    status=updated.status,
                    message=message,
                    waiting=load_waiting(updated),
                ),
                updated,
            )

        if waiting is not None:
            return await self._answer_waiting(db, task, waiting, user_input, reporter=reporter)

        if self._structurer is not None and user_input.text:
            task, message, paused_waiting, failed = await intake_step(
                db, task, user_input.text, self._structurer, gate=self._quality_gate, reporter=reporter
            )
            if failed or paused_waiting is not None:
                return CoordinatorOutcome(
                    reply=CoordinatorReply(
                        task_public_id=task.public_id,
                        status=task.status,
                        message=message,
                        waiting=paused_waiting,
                    ),
                    task=task,
                )

        return await self._prepare_confirmation(db, task)

    def _cancel(self, db: Session, task: AssistantTask) -> CoordinatorOutcome:
        result = apply_task_update(
            db,
            task,
            TaskUpdate(
                status=AssistantTaskStatus.CANCELLED,
                clear_waiting=True,
                action_actor="USER",
                action_name="cancel_task",
            ),
        )
        return CoordinatorOutcome(
            reply=CoordinatorReply(
                task_public_id=result.task.public_id,
                status=result.task.status,
                message="已取消本次任务，未写入的内容不会保存。",
            ),
            task=result.task,
        )

    async def _answer_waiting(
        self,
        db: Session,
        task: AssistantTask,
        waiting: TaskWaiting,
        user_input: AssistantInput,
        reporter: ProgressReporter | None = None,
    ) -> CoordinatorOutcome:
        if reporter is None:
            reporter = NullProgressReporter()
        """Waiting replies patch exactly one field; no model call happens."""

        if waiting.type == AssistantWaitingType.CONFIRMATION:
            return await self._answer_confirmation(db, task, user_input, reporter=reporter)
        if waiting.type == AssistantWaitingType.ACTIVITY_KIND:
            return await self._answer_activity_kind(db, task, user_input, reporter=reporter)
        if waiting.type == AssistantWaitingType.OBJECT_SELECTION:
            return await self._answer_object_selection(db, task, waiting, user_input)
        return await self._answer_field(db, task, waiting, user_input, reporter=reporter)

    async def _prepare_confirmation(self, db: Session, task: AssistantTask) -> CoordinatorOutcome:
        draft = load_draft(task)
        if draft.quality_score.status != "CANDIDATE":
            return await self._advance(db, task)
        if task.authority_json.get("frozen_activity_command"):
            raise InvalidTaskTransitionError("frozen activity requires its matching waiting action")
        time_text = (draft.next_follow_time.value or "").strip()
        source = next((record for record in reversed(draft.source_records) if time_text in record.text), None)
        next_follow_time_granularity = "UNKNOWN"
        if source is not None and time_text:
            resolved, granularity = parse_deadline(time_text, anchor=source.recorded_at)
            next_follow_time_granularity = granularity
            next_follow_time = resolved.replace(hour=9) if resolved is not None and granularity == "DATE" else resolved
        else:
            next_follow_time = resolve_follow_up_time(time_text, base=task.created_time) if time_text else None
            if time_text:
                _, next_follow_time_granularity = parse_deadline(time_text, anchor=task.created_time)
        if time_text and (
            next_follow_time is None
            or (
                draft.next_follow_time.status != "ACCEPTED"
                and not any(time_text in segment for segment in draft.source_segments)
            )
        ):
            waiting = TaskWaiting(
                type=AssistantWaitingType.FIELD,
                field="next_follow_time",
                question_id=f"q_time_{task.public_id}_{task.version}",
                prompt="下次跟进时间无法确定，请提供具体日期和时间。",
            )
            result = apply_task_update(
                db,
                task,
                TaskUpdate(
                    waiting=waiting,
                    action_actor="SYSTEM",
                    action_name="ask_follow_up_time",
                    action_result={"reason": "UNRESOLVED_TIME"},
                ),
            )
            return CoordinatorOutcome(
                CoordinatorReply(
                    task_public_id=result.task.public_id,
                    status=result.task.status,
                    message=waiting.prompt,
                    waiting=load_waiting(result.task),
                ),
                result.task,
            )
        customer_id = task.authority_json.get("customer_public_id")
        if customer_id:
            from app.crud.permission import permission_crud
            from app.services.customer_activity_access_policy import (
                CustomerActivityAccessDeniedError,
                CustomerActivityCustomerNotFoundError,
                customer_activity_access_policy,
            )

            codes = {
                permission.code for permission in permission_crud.get_user_permissions(db, task.user_id, task.team_id)
            }
            try:
                customer = customer_activity_access_policy.resolve_customer(
                    db,
                    customer_identifier=customer_id,
                    team_id=task.team_id,
                    user_id=task.user_id,
                    permission_codes=codes,
                )
            except CustomerActivityAccessDeniedError:
                return self._customer_permission_denied(db, task)
            except CustomerActivityCustomerNotFoundError:
                return self._ask_customer(db, task, code="NOT_FOUND")
        elif draft.customer.value:
            resolution = resolve_customer_candidates_for_assistant(
                db,
                team_id=task.team_id,
                user_id=task.user_id,
                customer_name=draft.customer.value,
            )
            if resolution.status == "RESOLVED":
                customer = resolution.customer
            elif resolution.status == "AMBIGUOUS":
                waiting = TaskWaiting(
                    type=AssistantWaitingType.OBJECT_SELECTION,
                    field="customer",
                    question_id=f"q_cust_{task.public_id}_{task.version}",
                    prompt="请选择这次沟通对应的客户。",
                    candidates=resolution.candidates,
                )
                result = apply_task_update(
                    db,
                    task,
                    TaskUpdate(
                        waiting=waiting,
                        action_actor="SYSTEM",
                        action_name="choose_customer",
                        action_result={"candidate_count": len(resolution.candidates)},
                    ),
                )
                return CoordinatorOutcome(
                    CoordinatorReply(
                        task_public_id=task.public_id,
                        status=task.status,
                        message=waiting.prompt,
                        waiting=load_waiting(result.task),
                    ),
                    result.task,
                )
            elif resolution.status == "DEPENDENCY_FAILURE":
                raise RuntimeError("customer resolution unavailable")
            elif resolution.status == "PERMISSION_DENIED":
                return self._customer_permission_denied(db, task)
            else:
                return self._ask_customer(db, task, code="NOT_FOUND")
        else:
            return self._ask_customer(db, task)
        updated, waiting = freeze_confirmation(
            db,
            task,
            customer=customer,
            next_follow_time=next_follow_time,
            next_follow_time_granularity=next_follow_time_granularity,
        )
        return CoordinatorOutcome(
            CoordinatorReply(
                task_public_id=updated.public_id, status=updated.status, message=waiting.prompt, waiting=waiting
            ),
            updated,
        )

    def _ask_customer(self, db: Session, task: AssistantTask, *, code: str | None = None) -> CoordinatorOutcome:
        waiting = TaskWaiting(
            type=AssistantWaitingType.FIELD,
            field="customer",
            question_id=f"q_customer_{task.public_id}_{task.version}",
            prompt="未找到对应客户，请核对并提供客户准确名称。" if code else "请提供客户准确名称。",
        )
        result = apply_task_update(
            db,
            task,
            TaskUpdate(
                waiting=waiting,
                error_code=code,
                action_actor="SYSTEM",
                action_name="ask_customer_name",
                action_result={"code": code} if code else {},
            ),
        )
        return CoordinatorOutcome(
            CoordinatorReply(
                task_public_id=task.public_id,
                status=task.status,
                message=waiting.prompt,
                waiting=load_waiting(result.task),
            ),
            result.task,
        )

    def _customer_permission_denied(self, db: Session, task: AssistantTask) -> CoordinatorOutcome:
        result = apply_task_update(
            db,
            task,
            TaskUpdate(
                error_code="PERMISSION_DENIED",
                action_actor="SYSTEM",
                action_name="customer_permission_denied",
                action_result={"code": "PERMISSION_DENIED"},
            ),
        )
        return CoordinatorOutcome(
            CoordinatorReply(
                task_public_id=task.public_id,
                status=task.status,
                message="没有权限记录该客户活动，请联系管理员确认客户访问权限。",
            ),
            result.task,
        )

    async def _answer_object_selection(
        self, db: Session, task: AssistantTask, waiting: TaskWaiting, user_input: AssistantInput
    ) -> CoordinatorOutcome:
        from app.crud.permission import permission_crud
        from app.services.customer_activity_access_policy import customer_activity_access_policy

        customer_id = user_input.choice
        if customer_id not in {item.get("id") for item in waiting.candidates}:
            raise InvalidTaskTransitionError("customer choice is not in the signed waiting card")
        codes = {permission.code for permission in permission_crud.get_user_permissions(db, task.user_id, task.team_id)}
        customer = customer_activity_access_policy.resolve_customer(
            db,
            customer_identifier=customer_id,
            team_id=task.team_id,
            user_id=task.user_id,
            permission_codes=codes,
        )
        result = apply_task_update(
            db,
            task,
            TaskUpdate(
                clear_waiting=True,
                authority=TaskAuthority(customer_public_id=customer.public_id),
                action_actor="USER",
                action_name="select_customer",
                action_result={"customer_public_id": customer.public_id},
            ),
        )
        return await self._prepare_confirmation(db, result.task)

    async def _answer_field(
        self,
        db: Session,
        task: AssistantTask,
        waiting: TaskWaiting,
        user_input: AssistantInput,
        reporter: ProgressReporter | None = None,
    ) -> CoordinatorOutcome:
        from app.services.assistant.intake_flow import _merge_text

        if reporter is None:
            reporter = NullProgressReporter()
        field_name = waiting.field or ""
        text = (user_input.text or "").strip()
        if not text:
            return CoordinatorOutcome(
                CoordinatorReply(
                    task_public_id=task.public_id,
                    status=task.status,
                    message=waiting.prompt,
                    waiting=waiting,
                ),
                task,
            )

        draft = load_draft(task)
        slot: DraftField | None = getattr(draft, field_name, None)
        if slot is None or field_name == "quality_score":
            raise ValueError(f"waiting field {field_name!r} is not a user-editable draft slot")
        explicit_none = user_input.choice == "EXPLICITLY_NONE"
        if explicit_none and field_name != "next_action":
            raise InvalidTaskTransitionError("explicit absence is only supported for next action")

        value = _merge_text(slot.value or "", text) if field_name == "content" else None if explicit_none else text
        status = (
            "EXPLICITLY_NONE"
            if explicit_none
            else "CANDIDATE"
            if field_name == "content" and self._structurer is not None
            else "ACCEPTED"
        )
        setattr(draft, field_name, DraftField(status=status, value=value))
        append_source(db, task, draft, text)
        if field_name != "customer":
            kind = task.activity_kind or "FOLLOW_UP"
            canonical_field = {
                "content": "content" if kind == "FOLLOW_UP" else "key_minutes",
                "next_action": "next_action" if kind == "FOLLOW_UP" else "next_step_summary",
                "next_follow_time": "next_follow_time_text",
                "meeting_subject": "meeting_subject",
            }.get(field_name)
            if canonical_field == "key_minutes" and self._structurer is None:
                minutes = list(draft.content_json.get("key_minutes") or [])
                if text not in minutes:
                    minutes.append(text)
                draft.content_json[canonical_field] = minutes
                draft.content = DraftField(status="CANDIDATE", value="\n".join(minutes))
            elif canonical_field is not None and (field_name != "content" or self._structurer is None):
                draft.content_json[canonical_field] = value or ""
            if explicit_none:
                draft.content_json["next_action_absence_reason"] = text
                draft.content_json["action_items"] = []
                draft.content_json["next_follow_time_text"] = ""
                draft.next_follow_time = DraftField(status="MISSING")
                reconcile_action_evidence(draft, kind)
            draft.quality_score = DraftField(status="MISSING")
            draft.score_reason = None
            draft.score_detail = {}

        result = apply_task_update(
            db,
            task,
            TaskUpdate(
                clear_waiting=True,
                draft=draft,
                action_actor="USER",
                action_name="submit_field",
                action_input={"field": field_name, "choice": user_input.choice, "text": text[:2000]},
                action_result={"accepted": True},
            ),
        )
        updated = result.task
        if field_name != "customer" and self._structurer is not None and self._quality_gate is not None:
            updated, message, paused, failed = await intake_step(
                db,
                updated,
                text,
                self._structurer,
                gate=self._quality_gate,
                reporter=reporter,
                from_waiting=True,
            )
            if failed or paused is not None:
                return CoordinatorOutcome(
                    CoordinatorReply(
                        task_public_id=updated.public_id,
                        status=updated.status,
                        message=message,
                        waiting=paused,
                    ),
                    updated,
                )
        return await self._prepare_confirmation(db, updated)

    async def _answer_confirmation(
        self,
        db: Session,
        task: AssistantTask,
        user_input: AssistantInput,
        reporter: ProgressReporter | None = None,
    ) -> CoordinatorOutcome:
        if reporter is None:
            reporter = NullProgressReporter()
        choice = (user_input.choice or "").strip().lower()

        if (task.waiting_field or "").startswith("proposal:"):
            from app.services.assistant.proposals import settle_proposal

            updated, message, start_followup = await settle_proposal(
                db, task, accepted=choice == "confirm", executor=self._proposal_executor
            )
            return CoordinatorOutcome(
                reply=CoordinatorReply(task_public_id=updated.public_id, status=updated.status, message=message),
                task=updated,
                start_followup=start_followup,
            )

        if self._writer is None:
            from app.services.assistant.turns import AssistantConfigurationError

            raise AssistantConfigurationError("confirmation submitted but no activity writer is configured")
        if choice == "confirm":
            import time as _time

            from app.services.assistant.events import stage as mk_stage

            reporter.stage_start(mk_stage("write"))
            _t0 = _time.monotonic()
            updated, message = await execute_confirmation(db, task, writer=self._writer)
            reporter.stage_done(mk_stage("write"), ms=int((_time.monotonic() - _t0) * 1000))
            return CoordinatorOutcome(
                reply=CoordinatorReply(task_public_id=updated.public_id, status=updated.status, message=message),
                task=updated,
                start_followup=any(item.get("kind") == "customer_activity" for item in updated.committed_json or []),
            )
        result = apply_task_update(
            db,
            task,
            TaskUpdate(
                clear_waiting=True,
                clear_frozen_activity_command=True,
                action_actor="USER",
                action_name="reject_confirmation",
                action_result={"reason": choice or "unspecified"},
            ),
        )
        return CoordinatorOutcome(
            CoordinatorReply(
                task_public_id=result.task.public_id,
                status=result.task.status,
                message="未写入客户活动；可补充内容后重新整理。",
            ),
            result.task,
        )

    async def _answer_activity_kind(
        self,
        db: Session,
        task: AssistantTask,
        user_input: AssistantInput,
        reporter: ProgressReporter | None = None,
    ) -> CoordinatorOutcome:
        if reporter is None:
            reporter = NullProgressReporter()
        kind = user_input.choice or ""
        allowed = {"FOLLOW_UP", "ONLINE_MEETING", "OFFLINE_MEETING"}
        if kind not in allowed:
            return CoordinatorOutcome(
                reply=CoordinatorReply(
                    task_public_id=task.public_id,
                    status=task.status,
                    message="请选择线上会议、线下会议或普通跟进。",
                    waiting=load_waiting(task),
                ),
                task=task,
            )
        result = apply_task_update(
            db,
            task,
            TaskUpdate(
                clear_waiting=True,
                activity_kind=kind,
                action_actor="USER",
                action_name="select_activity_kind",
                action_input={"kind": kind},
                action_result={"accepted": True, "choice": kind},
            ),
        )
        updated = result.task

        # Kind is now known: continue structuring from the original goal text
        # instead of letting the chooser end an unstructured task.
        if self._structurer is not None:
            original_text = updated.goal
            updated, message, paused_waiting, failed = await intake_step(
                db,
                updated,
                original_text,
                self._structurer,
                gate=self._quality_gate,
                reporter=reporter,
                accept_source=False,
            )
            if failed or paused_waiting is not None:
                return CoordinatorOutcome(
                    reply=CoordinatorReply(
                        task_public_id=updated.public_id,
                        status=updated.status,
                        message=message,
                        waiting=paused_waiting,
                    ),
                    task=updated,
                )

        return await self._prepare_confirmation(db, updated)

    async def _advance(self, db: Session, task: AssistantTask) -> CoordinatorOutcome:
        """No waiting: server-gated proposal flow, then chooser nomination."""

        draft = load_draft(task)
        if (
            draft.content.status == "ACCEPTED"
            and any(str(item.get("kind", "")) == "customer_activity" for item in task.committed_json or [])
            and task.status == AssistantTaskStatus.ACTIVE
        ):
            from app.services.assistant.proposals import offer_next_proposal

            proposed_task, message, offered = await offer_next_proposal(db, task)
            if offered or proposed_task.status == AssistantTaskStatus.COMPLETED:
                return CoordinatorOutcome(
                    reply=CoordinatorReply(
                        task_public_id=proposed_task.public_id,
                        status=proposed_task.status,
                        message=message,
                        waiting=load_waiting(proposed_task),
                    ),
                    task=proposed_task,
                )
        if task.budget_steps >= task.budget_max_steps:
            result = apply_task_update(
                db,
                task,
                TaskUpdate(
                    error_code="CHOOSER_BUDGET_EXHAUSTED",
                    action_actor="SYSTEM",
                    action_name="budget_exhausted",
                    action_result={"steps": task.budget_steps},
                ),
            )
            return CoordinatorOutcome(
                CoordinatorReply(
                    task_public_id=result.task.public_id,
                    status=result.task.status,
                    message="自动处理次数已用完，请人工处理；本次没有写入新活动。",
                ),
                result.task,
            )
        reserved = apply_task_update(
            db,
            task,
            TaskUpdate(
                action_actor="SYSTEM",
                action_name="chooser_nomination",
                action_result={"reserved": True},
            ),
        )
        task = reserved.task
        try:
            decision = await self._next_action_chooser.choose(task)
        except (AssistantLLMError, TimeoutError, ValueError, TypeError, ValidationError) as exc:
            result = apply_task_update(
                db,
                task,
                TaskUpdate(
                    error_code="CHOOSER_UNAVAILABLE",
                    action_actor="SYSTEM",
                    action_name="chooser_failed",
                    action_result={"error_type": type(exc).__name__},
                ),
            )
            return CoordinatorOutcome(
                CoordinatorReply(
                    task_public_id=result.task.public_id,
                    status=result.task.status,
                    message="自动处理暂不可用，请稍后重试；本次没有写入新活动。",
                ),
                result.task,
            )
        if decision.action == "end" and not any(
            receipt.get("kind") == "customer_activity" for receipt in (task.committed_json or [])
        ):
            result = apply_task_update(
                db,
                task,
                TaskUpdate(
                    error_code="END_NOT_ALLOWED",
                    action_actor="SYSTEM",
                    action_name="reject_premature_end",
                    action_result={"reason": "no_committed_activity"},
                ),
            )
            return CoordinatorOutcome(
                CoordinatorReply(
                    task_public_id=result.task.public_id,
                    status=result.task.status,
                    message="尚未写入客户活动，无法结束；请补充所需内容。",
                ),
                result.task,
            )
        if decision.action == "end":
            result = apply_task_update(
                db,
                task,
                TaskUpdate(
                    status=AssistantTaskStatus.COMPLETED,
                    action_actor="MODEL",
                    action_name="end",
                    action_result={"reason": decision.parameters.get("reason", "goal_reached")},
                ),
            )
            return CoordinatorOutcome(
                CoordinatorReply(
                    task_public_id=result.task.public_id,
                    status=result.task.status,
                    message="本次记录已处理完成。",
                ),
                result.task,
            )
        if decision.action == "ask_field":
            field = decision.parameters.get("field")
            prompt = decision.parameters.get("prompt")
            allowed = {"customer", "content", "next_action", "next_follow_time"}
            if (
                field in allowed
                and isinstance(prompt, str)
                and prompt.strip()
                and getattr(draft, field).status not in {"ACCEPTED", "EXPLICITLY_NONE"}
            ):
                return self._ask_field(db, task, decision.parameters)
        # Unknown nominations fail closed: recorded, task stays queryable.
        result = apply_task_update(
            db,
            task,
            TaskUpdate(
                error_code="UNKNOWN_ACTION_NOMINATED",
                action_actor="MODEL",
                action_name=decision.action,
                action_result={"accepted": False, "reason": "unknown action for current state"},
            ),
        )
        return CoordinatorOutcome(
            reply=CoordinatorReply(
                task_public_id=result.task.public_id,
                status=result.task.status,
                message="我暂时不确定下一步该怎么处理，请稍后再试。",
            ),
            task=result.task,
        )

    def _ask_field(self, db: Session, task: AssistantTask, parameters: dict[str, object]) -> CoordinatorOutcome:
        field_name = str(parameters.get("field", ""))
        if field_name not in {"customer", "content", "next_action", "next_follow_time"}:
            raise ValueError(f"cannot ask for unknown field {field_name!r}")
        result = apply_task_update(
            db,
            task,
            TaskUpdate(
                error_code="BUSINESS_GAP",
                action_actor="SYSTEM",
                action_name="business_gap",
                action_result={"field": field_name},
            ),
        )
        task = result.task
        waiting = TaskWaiting(
            type=AssistantWaitingType.FIELD,
            field=field_name,
            question_id=f"q_{task.public_id}_{task.version + 1}",
            prompt=str(parameters.get("prompt", f"请补充{field_name}")),
        )
        result = apply_task_update(
            db,
            task,
            TaskUpdate(
                waiting=waiting,
                action_actor="MODEL",
                action_name="ask_field",
                action_input={"field": field_name},
                action_result={"paused": True, "prompt": waiting.prompt},
            ),
        )
        return CoordinatorOutcome(
            reply=CoordinatorReply(
                task_public_id=result.task.public_id,
                status=result.task.status,
                message=waiting.prompt,
                waiting=waiting,
            ),
            task=result.task,
        )
