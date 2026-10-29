"""Coordinate durable intake, typed waits, frozen writes and CRM proposals."""
# ruff: noqa: RUF001

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.services.assistant.confirmation import ActivityWriter
    from app.services.assistant.intake import KindStructurer
    from app.services.assistant.quality_gate import QualityGate

from app.models.assistant import AssistantTask, AssistantTaskStatus, AssistantWaitingType
from app.services.assistant.action_evidence import append_source, parse_deadline, reconcile_action_evidence
from app.services.assistant.confirmation import execute_confirmation, freeze_confirmation
from app.services.assistant.contracts import DraftField, TaskAuthority, TaskDraft, TaskWaiting
from app.services.assistant.customer_resolution import resolve_customer_candidates_for_assistant
from app.services.assistant.events import NullProgressReporter, ProgressReporter
from app.services.assistant.intake_flow import intake_step, kind_waiting, raise_quality_gate_failure
from app.services.assistant.llm import AssistantLLMError
from app.services.assistant.task_state import (
    InvalidTaskTransitionError,
    TaskUpdate,
    apply_task_update,
    load_authority,
    load_draft,
    load_waiting,
)
from app.utils.time import resolve_follow_up_time

logger = logging.getLogger(__name__)


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
    card: str | None = None


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
        follow_up: object | None = None,
    ) -> None:
        self._next_action_chooser = next_action_chooser
        self._structurer = structurer
        self._writer = writer
        self._proposal_executor = proposal_executor
        self._quality_gate = quality_gate
        self._follow_up = follow_up

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
            handled = await self._open_follow_up_or_none(db, task)
            if handled is not None:
                return handled
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
            if self._follow_up is not None and task.activity_kind not in {"ONLINE_MEETING", "OFFLINE_MEETING"}:
                begun = await self._begin_follow_up(db, task, user_input.text, reporter, accept_source=True)
                if isinstance(begun, CoordinatorOutcome):
                    return begun
                task = begun
            else:
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
                action_input={"source": "explicit_user_cancel", "input_kind": "cancel"},
            ),
        )
        logger.info(
            "assistant_task_cancelled source=explicit_user_cancel task=%s",
            result.task.public_id,
        )
        return CoordinatorOutcome(
            reply=CoordinatorReply(
                task_public_id=result.task.public_id,
                status=result.task.status,
                message="当前这件已停下，之前的对话和已写入的记录仍保留。",
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
            return await self._answer_object_selection(db, task, waiting, user_input, reporter=reporter)
        if waiting.type == AssistantWaitingType.FOLLOW_UP_DISPOSITION:
            return await self._answer_open_follow_up(db, task, user_input)
        if waiting.field == "temporal_choice":
            return await self._answer_temporal_choice(db, task, waiting, user_input, reporter=reporter)
        return await self._answer_field(db, task, waiting, user_input, reporter=reporter)

    async def _prepare_confirmation(self, db: Session, task: AssistantTask) -> CoordinatorOutcome:
        draft = load_draft(task)
        if draft.quality_score.status != "CANDIDATE":
            return await self._advance(db, task)
        if task.authority_json.get("frozen_activity_command"):
            raise InvalidTaskTransitionError("frozen activity requires its matching waiting action")
        temporal = draft.content_json.get("temporal_evidence")
        if isinstance(temporal, dict) and temporal.get("version") == "temporal-evidence-v1":
            gated = await self._gate_temporal_evidence(db, task, draft)
            if isinstance(gated, CoordinatorOutcome):
                return gated
            task, next_follow_time, next_follow_time_granularity = gated
            draft = load_draft(task)
        else:
            time_text = (draft.next_follow_time.value or "").strip()
            source = next((record for record in reversed(draft.source_records) if time_text in record.text), None)
            next_follow_time_granularity = "UNKNOWN"
            if source is not None and time_text:
                resolved, granularity = parse_deadline(time_text, anchor=source.recorded_at)
                next_follow_time_granularity = granularity
                if resolved is not None and granularity == "DATE":
                    next_follow_time = resolved.replace(hour=9)
                else:
                    next_follow_time = resolved
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
        context_card = None
        if self._follow_up is not None and (task.activity_kind or "") == "FOLLOW_UP":
            attached = await self._attach_follow_up_context(db, task, customer)
            if isinstance(attached, CoordinatorOutcome):
                return attached
            task, context_card = attached
        updated, waiting = freeze_confirmation(
            db,
            task,
            customer=customer,
            next_follow_time=next_follow_time,
            next_follow_time_granularity=next_follow_time_granularity,
            context_card=context_card,
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
        self,
        db: Session,
        task: AssistantTask,
        waiting: TaskWaiting,
        user_input: AssistantInput,
        reporter: ProgressReporter | None = None,
    ) -> CoordinatorOutcome:
        if reporter is None:
            reporter = NullProgressReporter()
        from app.crud.permission import permission_crud
        from app.services.customer_activity_access_policy import customer_activity_access_policy

        if waiting.field == "opportunity":
            return await self._answer_opportunity_selection(db, task, waiting, user_input)
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
                clear_follow_up_opportunity=True,
                authority=TaskAuthority(customer_public_id=customer.public_id),
                action_actor="USER",
                action_name="select_customer",
                action_result={"customer_public_id": customer.public_id},
            ),
        )
        return await self._continue_after_customer(db, result.task, reporter=reporter)


    async def _gate_temporal_evidence(
        self, db: Session, task: AssistantTask, draft: TaskDraft
    ) -> CoordinatorOutcome | tuple[AssistantTask, object, str]:
        from app.services.assistant.temporal_evidence import project_draft, resolved_sales_follow_up, temporal_waiting

        project_draft(draft)
        spec = temporal_waiting(draft)
        if spec is not None:
            raw_candidates = spec.get("candidates")
            if isinstance(raw_candidates, list):
                candidates = [item for item in raw_candidates if isinstance(item, dict)]
            else:
                candidates = []
            waiting = TaskWaiting(
                type=AssistantWaitingType.FIELD,
                field="temporal_choice" if candidates else "next_follow_time",
                question_id=f"q_time_{task.public_id}_{task.version}",
                prompt=str(spec["prompt"]),
                candidates=candidates,
            )
            result = apply_task_update(
                db,
                task,
                TaskUpdate(
                    draft=draft,
                    waiting=waiting,
                    action_actor="SYSTEM",
                    action_name="ask_temporal_evidence",
                    action_result={"reason": spec["reason"], "candidate_count": len(candidates)},
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
        resolved, granularity = resolved_sales_follow_up(draft)
        result = apply_task_update(
            db,
            task,
            TaskUpdate(draft=draft, action_actor="SYSTEM", action_name="project_temporal_evidence"),
        )
        return result.task, resolved, granularity

    async def _answer_temporal_choice(
        self,
        db: Session,
        task: AssistantTask,
        waiting: TaskWaiting,
        user_input: AssistantInput,
        reporter: ProgressReporter | None = None,
    ) -> CoordinatorOutcome:
        from app.services.assistant.temporal_evidence import (
            TemporalContractError,
            apply_temporal_choice,
            match_temporal_choice_id,
        )

        if reporter is None:
            reporter = NullProgressReporter()
        choice = (user_input.choice or "").strip()
        if not choice:
            choice = match_temporal_choice_id(waiting.candidates, user_input.text or "") or ""
        offered = {str(item.get("id")) for item in waiting.candidates if isinstance(item, dict)}
        if not choice or choice not in offered:
            return CoordinatorOutcome(
                CoordinatorReply(
                    task_public_id=task.public_id, status=task.status, message=waiting.prompt, waiting=waiting
                ),
                task,
            )
        draft = load_draft(task)
        try:
            apply_temporal_choice(draft, choice)
        except TemporalContractError:
            return CoordinatorOutcome(
                CoordinatorReply(
                    task_public_id=task.public_id, status=task.status, message=waiting.prompt, waiting=waiting
                ),
                task,
            )
        result = apply_task_update(
            db,
            task,
            TaskUpdate(
                clear_waiting=True,
                draft=draft,
                action_actor="USER",
                action_name="choose_temporal_evidence",
                action_input={"choice": choice},
                action_result={"accepted": True},
            ),
        )
        updated = result.task
        if self._quality_gate is not None:
            scored = await self._rescore_temporal_choice(db, updated, reporter)
            if isinstance(scored, CoordinatorOutcome):
                return scored
            updated = scored
        return await self._prepare_confirmation(db, updated)

    async def _rescore_temporal_choice(
        self, db: Session, task: AssistantTask, _reporter: ProgressReporter
    ) -> CoordinatorOutcome | AssistantTask:
        from typing import cast

        gate = cast("QualityGate", self._quality_gate)
        draft = load_draft(task)
        try:
            gate_outcome = await gate.evaluate(
                db,
                team_id=task.team_id,
                user_text="\n".join(draft.source_segments),
                content=draft.content.value or "",
                next_action=draft.next_action.value or "",
                kind=task.activity_kind or "FOLLOW_UP",
                content_json=draft.content_json,
            )
        except (AssistantLLMError, TimeoutError, ValueError, TypeError) as exc:
            raise_quality_gate_failure(db, task, exc)
        if not gate_outcome.passed:
            gap = TaskWaiting(
                type=AssistantWaitingType.FIELD,
                field=gate_outcome.gap_field or "content",
                question_id=f"q_gap_{task.public_id}_{task.version}",
                prompt=gate_outcome.question or "请补充这次沟通的关键信息。",
            )
            result = apply_task_update(
                db,
                task,
                TaskUpdate(waiting=gap, action_actor="SYSTEM", action_name="ask_quality_gap"),
            )
            return CoordinatorOutcome(
                CoordinatorReply(
                    task_public_id=result.task.public_id,
                    status=result.task.status,
                    message=gap.prompt,
                    waiting=load_waiting(result.task),
                ),
                result.task,
            )
        draft.quality_score = DraftField(status="CANDIDATE", value=str(gate_outcome.score))
        draft.score_reason = gate_outcome.reason
        draft.score_detail = gate_outcome.detail or {}
        result = apply_task_update(
            db,
            task,
            TaskUpdate(
                draft=draft,
                action_actor="SYSTEM",
                action_name="quality_gate",
                action_result={"passed": True, "score": gate_outcome.score},
            ),
        )
        return result.task

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
        if self._follow_up is not None and field_name == "customer" and (task.activity_kind or "") == "FOLLOW_UP":
            return await self._answer_follow_up_customer(db, task, text, reporter)

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
        if user_input.kind == "revise_activity_kind":
            return self._revise_activity_kind(db, task, user_input.choice or "")
        if choice == "confirm":
            command = load_authority(task).frozen_activity_command
            if isinstance(command, dict) and command.get("channel_status") == "required":
                return CoordinatorOutcome(
                    CoordinatorReply(
                        task_public_id=task.public_id,
                        status=task.status,
                        message="请先选择活动类型。",
                        waiting=load_waiting(task),
                    ),
                    task,
                )
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
        if self._follow_up is not None and kind == "FOLLOW_UP":
            begun = await self._begin_follow_up(db, updated, updated.goal, reporter, accept_source=False)
            if isinstance(begun, CoordinatorOutcome):
                return begun
            return await self._prepare_confirmation(db, begun)
        if kind in {"ONLINE_MEETING", "OFFLINE_MEETING"}:
            from app.services.assistant.activity_channel import apply_channel_resolution, selected_kind

            drafted = apply_channel_resolution(load_draft(updated), selected_kind(kind))
            updated = apply_task_update(
                db,
                updated,
                TaskUpdate(
                    draft=drafted,
                    action_actor="SYSTEM",
                    action_name="remember_activity_kind",
                    action_result={"kind": kind, "source": "user"},
                ),
            ).task
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

    async def _open_follow_up_or_none(self, db: Session, task: AssistantTask) -> CoordinatorOutcome | None:
        from app.services.assistant.open_follow_up_disposition import advance_open_follow_up

        outcome = await advance_open_follow_up(db, task)
        if outcome is None:
            return None
        return CoordinatorOutcome(
            CoordinatorReply(
                task_public_id=outcome.task.public_id,
                status=outcome.task.status,
                message=outcome.message,
                waiting=load_waiting(outcome.task),
                card="follow_up_disposition",
            ),
            outcome.task,
            start_followup=outcome.start_followup,
        )

    async def _answer_open_follow_up(
        self, db: Session, task: AssistantTask, user_input: AssistantInput,
    ) -> CoordinatorOutcome:
        from app.services.assistant.open_follow_up_disposition import settle_open_follow_up

        outcome = await settle_open_follow_up(db, task, (user_input.choice or "").strip())
        return CoordinatorOutcome(
            CoordinatorReply(
                task_public_id=outcome.task.public_id,
                status=outcome.task.status,
                message=outcome.message,
                waiting=load_waiting(outcome.task),
                card="follow_up_disposition",
            ),
            outcome.task,
            start_followup=outcome.start_followup,
        )

    async def _advance(self, db: Session, task: AssistantTask) -> CoordinatorOutcome:
        """No waiting: server-gated proposal flow, then chooser nomination."""

        draft = load_draft(task)
        if (
            draft.content.status == "ACCEPTED"
            and any(str(item.get("kind", "")) == "customer_activity" for item in task.committed_json or [])
            and task.status == AssistantTaskStatus.ACTIVE
        ):
            handled = await self._open_follow_up_or_none(db, task)
            if handled is not None:
                return handled
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


    async def _classify_channel(
        self,
        db: Session,
        task: AssistantTask,
        user_text: str,
        reporter: ProgressReporter,
        *,
        accept_source: bool,
    ) -> CoordinatorOutcome | AssistantTask:
        import time

        from app.services.assistant.activity_channel import apply_channel_resolution, resolve_channel
        from app.services.assistant.events import stage as mk_stage

        reporter.stage_start(mk_stage("classify"))
        started = time.monotonic()
        decision = None
        model_failed = False
        try:
            decision = await self._structurer.classify(db, team_id=task.team_id, user_text=user_text)
        except AssistantLLMError:
            model_failed = True
        reporter.stage_done(mk_stage("classify"), ms=int((time.monotonic() - started) * 1000))
        resolution = resolve_channel(user_text, decision, model_failed=model_failed)
        draft = load_draft(task)
        if resolution.status == "family_unclear":
            if accept_source:
                append_source(db, task, draft, user_text)
            waiting = kind_waiting(task)
            result = apply_task_update(
                db,
                task,
                TaskUpdate(
                    draft=draft,
                    waiting=waiting,
                    action_actor="SYSTEM",
                    action_name="ask_activity_kind",
                    action_result={"reason": resolution.reason},
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
        allowed_families = {"FOLLOW_UP", "ONLINE_MEETING", "OFFLINE_MEETING"}
        family = resolution.family if resolution.family in allowed_families else "FOLLOW_UP"
        draft = apply_channel_resolution(draft, resolution)
        result = apply_task_update(
            db,
            task,
            TaskUpdate(
                draft=draft,
                activity_kind=family,
                action_actor="SYSTEM",
                action_name="set_activity_kind",
                action_result={
                    "kind": resolution.kind,
                    "family": family,
                    "source": resolution.source or "unresolved",
                    "status": resolution.status,
                },
            ),
        )
        return result.task

    def _revise_activity_kind(self, db: Session, task: AssistantTask, kind: str) -> CoordinatorOutcome:
        from app.services.assistant.confirmation import revise_frozen_activity_kind

        try:
            updated, waiting = revise_frozen_activity_kind(db, task, kind)
        except ValueError:
            return CoordinatorOutcome(
                CoordinatorReply(
                    task_public_id=task.public_id,
                    status=task.status,
                    message="这个活动类型不在可修改范围内。",
                    waiting=load_waiting(task),
                ),
                task,
            )
        return CoordinatorOutcome(
            CoordinatorReply(
                task_public_id=updated.public_id,
                status=updated.status,
                message=waiting.prompt,
                waiting=waiting,
            ),
            updated,
        )

    async def _begin_follow_up(
        self,
        db: Session,
        task: AssistantTask,
        user_text: str,
        reporter: ProgressReporter,
        *,
        accept_source: bool,
    ) -> CoordinatorOutcome | AssistantTask:
        """Classify, bind the customer, then structure. Meetings stay on the old intake path."""

        if self._structurer is None or self._follow_up is None:
            raise RuntimeError("follow-up context requires a structurer")
        kind = task.activity_kind
        needs_channel = kind is None or (kind == "FOLLOW_UP" and load_draft(task).channel_status is None)
        if needs_channel:
            classified = await self._classify_channel(
                db, task, user_text, reporter, accept_source=accept_source and kind is None
            )
            if isinstance(classified, CoordinatorOutcome):
                return classified
            task = classified
            kind = task.activity_kind
        if kind != "FOLLOW_UP":
            updated, message, paused, failed = await intake_step(
                db, task, user_text, self._structurer, gate=self._quality_gate, reporter=reporter,
                accept_source=accept_source,
            )
            if failed or paused is not None:
                return CoordinatorOutcome(
                    CoordinatorReply(
                        task_public_id=updated.public_id, status=updated.status, message=message, waiting=paused
                    ),
                    updated,
                )
            return updated
        if not load_authority(task).customer_public_id:
            try:
                customer_name = await self._follow_up.locate_customer(db, team_id=task.team_id, user_text=user_text)
            except AssistantLLMError:
                result = apply_task_update(
                    db,
                    task,
                    TaskUpdate(
                        error_code="CUSTOMER_LOCATOR_UNAVAILABLE",
                        action_actor="SYSTEM",
                        action_name="locate_customer",
                        action_result={"accepted": False, "retryable": True},
                    ),
                )
                return CoordinatorOutcome(
                    CoordinatorReply(
                        task_public_id=result.task.public_id,
                        status=result.task.status,
                        message="客户暂时没有识别出来，请稍后重试。",
                    ),
                    result.task,
                )
            if not str(customer_name or "").strip():
                draft = load_draft(task)
                if accept_source:
                    append_source(db, task, draft, user_text)
                    apply_task_update(
                        db,
                        task,
                        TaskUpdate(draft=draft, action_actor="USER", action_name="accept_source"),
                    )
                return self._ask_customer(db, task)
            resolution = resolve_customer_candidates_for_assistant(
                db, team_id=task.team_id, user_id=task.user_id, customer_name=str(customer_name)
            )
            if resolution.status == "AMBIGUOUS":
                draft = load_draft(task)
                if accept_source:
                    append_source(db, task, draft, user_text)
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
                        draft=draft,
                        waiting=waiting,
                        action_actor="SYSTEM",
                        action_name="choose_customer",
                        action_result={"candidate_count": len(resolution.candidates)},
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
            if resolution.status == "RESOLVED" and resolution.customer is not None:
                draft = load_draft(task)
                draft.customer = DraftField(status="ACCEPTED", value=resolution.customer.account_name)
                if accept_source:
                    append_source(db, task, draft, user_text)
                result = apply_task_update(
                    db,
                    task,
                    TaskUpdate(
                        draft=draft,
                        authority=TaskAuthority(customer_public_id=resolution.customer.public_id),
                        action_actor="SYSTEM",
                        action_name="bind_customer",
                        action_result={"customer_public_id": resolution.customer.public_id},
                    ),
                )
                task = result.task
            elif resolution.status == "DEPENDENCY_FAILURE":
                raise RuntimeError("customer resolution unavailable")
            elif resolution.status == "PERMISSION_DENIED":
                return self._customer_permission_denied(db, task)
            else:
                draft = load_draft(task)
                if accept_source:
                    append_source(db, task, draft, user_text)
                    apply_task_update(
                        db, task, TaskUpdate(draft=draft, action_actor="USER", action_name="accept_source")
                    )
                return self._ask_customer(db, task, code="NOT_FOUND")
        segments = load_draft(task).source_segments
        fresh = accept_source and bool(user_text.strip()) and user_text.strip() not in segments
        intake_text = user_text if fresh else ("\n".join(segments) or user_text)
        updated, message, paused, failed = await intake_step(
            db,
            task,
            intake_text,
            self._structurer,
            gate=self._quality_gate,
            reporter=reporter,
            accept_source=fresh,
        )
        if failed or paused is not None:
            return CoordinatorOutcome(
                CoordinatorReply(
                    task_public_id=updated.public_id, status=updated.status, message=message, waiting=paused
                ),
                updated,
            )
        return updated

    async def _continue_after_customer(
        self, db: Session, task: AssistantTask, *, reporter: ProgressReporter
    ) -> CoordinatorOutcome:
        draft = load_draft(task)
        needs_structure = (
            self._follow_up is not None
            and (task.activity_kind or "") == "FOLLOW_UP"
            and self._structurer is not None
            and draft.quality_score.status != "CANDIDATE"
        )
        if needs_structure:
                text = "\n".join(draft.source_segments) or task.goal
                updated, message, paused, failed = await intake_step(
                    db,
                    task,
                    text,
                    self._structurer,
                    gate=self._quality_gate,
                    reporter=reporter,
                    accept_source=False,
                )
                if failed or paused is not None:
                    return CoordinatorOutcome(
                        CoordinatorReply(
                            task_public_id=updated.public_id, status=updated.status, message=message, waiting=paused
                        ),
                        updated,
                    )
                task = updated
        return await self._prepare_confirmation(db, task)

    async def _answer_follow_up_customer(
        self, db: Session, task: AssistantTask, customer_name: str, reporter: ProgressReporter
    ) -> CoordinatorOutcome:
        resolution = resolve_customer_candidates_for_assistant(
            db, team_id=task.team_id, user_id=task.user_id, customer_name=customer_name
        )
        if resolution.status == "AMBIGUOUS":
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
                    clear_waiting=True,
                    clear_follow_up_opportunity=True,
                    waiting=waiting,
                    action_actor="SYSTEM",
                    action_name="choose_customer",
                    action_result={"candidate_count": len(resolution.candidates)},
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
        if resolution.status != "RESOLVED" or resolution.customer is None:
            if resolution.status == "DEPENDENCY_FAILURE":
                raise RuntimeError("customer resolution unavailable")
            if resolution.status == "PERMISSION_DENIED":
                return self._customer_permission_denied(db, task)
            return self._ask_customer(db, task, code="NOT_FOUND")
        draft = load_draft(task)
        draft.customer = DraftField(status="ACCEPTED", value=resolution.customer.account_name)
        result = apply_task_update(
            db,
            task,
            TaskUpdate(
                clear_waiting=True,
                clear_follow_up_opportunity=True,
                draft=draft,
                authority=TaskAuthority(customer_public_id=resolution.customer.public_id),
                action_actor="USER",
                action_name="submit_customer",
                action_result={"customer_public_id": resolution.customer.public_id},
            ),
        )
        return await self._continue_after_customer(db, result.task, reporter=reporter)

    async def _answer_opportunity_selection(
        self, db: Session, task: AssistantTask, waiting: TaskWaiting, user_input: AssistantInput
    ) -> CoordinatorOutcome:
        from app.services.assistant.follow_up_context import load_visible_opportunity

        choice = user_input.choice or ""
        if choice not in {item.get("id") for item in waiting.candidates}:
            raise InvalidTaskTransitionError("opportunity choice is not in the signed waiting card")
        customer_id = load_authority(task).customer_public_id
        if not customer_id:
            raise InvalidTaskTransitionError("opportunity choice requires a bound customer")
        from app.crud.permission import permission_crud
        from app.services.customer_activity_access_policy import customer_activity_access_policy

        codes = {item.code for item in permission_crud.get_user_permissions(db, task.user_id, task.team_id)}
        customer = customer_activity_access_policy.resolve_customer(
            db,
            customer_identifier=customer_id,
            team_id=task.team_id,
            user_id=task.user_id,
            permission_codes=codes,
        )
        row = load_visible_opportunity(
            db,
            team_id=task.team_id,
            user_id=task.user_id,
            customer_id=int(customer.id),
            public_id=choice,
            permission_codes=codes,
        )
        if row is None:
            raise InvalidTaskTransitionError("opportunity choice is no longer visible")
        result = apply_task_update(
            db,
            task,
            TaskUpdate(
                clear_waiting=True,
                authority=TaskAuthority(
                    customer_public_id=customer.public_id,
                    opportunity_public_id=row.public_id,
                    opportunity_stage_name=row.current_stage_name or "",
                ),
                action_actor="USER",
                action_name="select_opportunity",
                action_result={"opportunity_public_id": row.public_id},
            ),
        )
        return await self._prepare_confirmation(db, result.task)

    async def _attach_follow_up_context(
        self, db: Session, task: AssistantTask, customer: object
    ) -> CoordinatorOutcome | tuple[AssistantTask, dict[str, object]]:
        from app.services.assistant.follow_up_context import OPPORTUNITY_PROMPT

        if self._follow_up is None:
            raise RuntimeError("follow-up context is not configured")
        authority = load_authority(task)
        draft = load_draft(task)
        user_text = "\n".join(draft.source_segments)
        pack = self._follow_up.read_evidence(db, team_id=task.team_id, user_id=task.user_id, customer=customer)
        choice = await self._follow_up.choose_opportunity(
            db,
            team_id=task.team_id,
            user_id=task.user_id,
            customer=customer,
            user_text=user_text,
            pack=pack,
            bound_public_id=authority.opportunity_public_id,
            bound_stage=authority.opportunity_stage_name,
        )
        if choice.kind == "ask":
            waiting = TaskWaiting(
                type=AssistantWaitingType.OBJECT_SELECTION,
                field="opportunity",
                question_id=f"q_opp_{task.public_id}_{task.version}",
                prompt=OPPORTUNITY_PROMPT,
                candidates=[dict(item) for item in choice.candidates],
            )
            result = apply_task_update(
                db,
                task,
                TaskUpdate(
                    clear_follow_up_opportunity=True,
                    waiting=waiting,
                    action_actor="SYSTEM",
                    action_name="choose_opportunity",
                    action_result={"candidate_count": len(choice.candidates)},
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
        if choice.kind == "bound" and choice.public_id:
            result = apply_task_update(
                db,
                task,
                TaskUpdate(
                    authority=TaskAuthority(
                        customer_public_id=customer.public_id,
                        opportunity_public_id=choice.public_id,
                        opportunity_stage_name=choice.stage or "",
                    ),
                    action_actor="SYSTEM",
                    action_name="bind_opportunity",
                    action_result={"opportunity_public_id": choice.public_id},
                ),
            )
            task = result.task
        else:
            result = apply_task_update(
                db,
                task,
                TaskUpdate(
                    clear_follow_up_opportunity=True,
                    action_actor="SYSTEM",
                    action_name="clear_opportunity",
                    action_result={"reason": choice.kind},
                ),
            )
            task = result.task
        card = await self._follow_up.judge(
            db, team_id=task.team_id, user_text=user_text, pack=pack, choice=choice
        )
        return task, card.as_command()

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
