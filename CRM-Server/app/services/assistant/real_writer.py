"""Write a frozen Assistant 2.0 activity and its receipt in the caller's transaction."""
# ruff: noqa: RUF001

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy.exc import DataError, SQLAlchemyError

from app.crud.permission import permission_crud
from app.crud.sales_commitment import follow_up_task_crud
from app.schemas.customer_activity import CustomerActivityCreate
from app.services.assistant.activity_edit import persisted_communication_time
from app.services.assistant.confirmation import (
    FollowUpProjectionReceipt,
    WriteActivityResult,
    command_fingerprint,
    normalize_projection_status,
)
from app.services.assistant.failure_contract import AssistantFailureCode, AssistantStageFailure
from app.services.customer_activity_access_policy import (
    CustomerActivityAccessDeniedError,
    CustomerActivityCustomerNotFoundError,
    customer_activity_access_policy,
)
from app.services.customer_activity_write_service import (
    CustomerActivityFinalization,
    CustomerActivitySubmissionConflictError,
    customer_activity_write_service,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.assistant import AssistantTask


class RealActivityWriter:
    """Recheck the frozen customer identity and stage one canonical activity."""

    async def write_activity(
        self, db: Session, *, task: AssistantTask, command: dict[str, object]
    ) -> WriteActivityResult:
        if (command.get("team_id") != task.team_id or command.get("user_id") != task.user_id
                or command.get("fingerprint") != command_fingerprint(command)):
            raise ValueError("frozen activity command does not belong to this task")
        permissions = {permission.code for permission in permission_crud.get_user_permissions(
            db, task.user_id, task.team_id
        )}
        try:
            customer = customer_activity_access_policy.resolve_customer(
                db, customer_identifier=str(command["customer_public_id"]),
                team_id=task.team_id, user_id=task.user_id, permission_codes=permissions,
            )
        except (CustomerActivityAccessDeniedError, CustomerActivityCustomerNotFoundError):
            return WriteActivityResult(False, None, "PERMISSION_DENIED")

        from app.services.assistant.turns import AssistantActivityCommitUnknownError

        team_id = int(task.team_id)
        task_public_id = task.public_id
        customer_id = int(customer.id)
        submission_id = str(command["submission_id"])
        expected_fingerprint = str(command["fingerprint"])
        try:
            existing = customer_activity_write_service.activity_crud.get_by_submission_id(
                db, team_id=team_id, submission_id=submission_id
            )
        except SQLAlchemyError as exc:
            raise AssistantActivityCommitUnknownError() from exc
        if existing is not None and (
            existing.submission_fingerprint != expected_fingerprint
            or existing.submission_source != "ASSISTANT_2"
            or existing.customer_id is None
            or int(existing.customer_id) != customer_id
        ):
            raise AssistantActivityCommitUnknownError()
        next_action = command.get("next_action")
        content_json = command["content_json"]
        score = int(command["score"])
        communication_time = (
            persisted_communication_time(content_json)
            if isinstance(content_json, dict)
            else None
        )
        obj_in = CustomerActivityCreate(
            activity_kind=str(command["activity_kind"]),
            title=str(command["title"]), summary=str(command["summary"]),
            source_content=str(command["source_content"]),
            content_json=content_json,
            occurred_at=communication_time[0] if communication_time is not None else None,
            next_action=str(next_action) if next_action else None,
            next_action_source="USER" if next_action else None,
            submission_source="ASSISTANT_2", submission_id=str(command["submission_id"]),
            submission_fingerprint=str(command["fingerprint"]),
        )
        finalization = CustomerActivityFinalization(
            title=obj_in.title, summary=obj_in.summary, content_json=content_json,
            next_action=obj_in.next_action, next_action_source=obj_in.next_action_source,
            next_follow_time=(
                datetime.fromisoformat(str(command["next_follow_time"])) if command.get("next_follow_time") else None
            ),
            next_follow_time_source="USER" if command.get("next_follow_time") else None,
            effectiveness_score=score, effectiveness_is_valid=score >= 60,
            effectiveness_reason=str(command["score_reason"]),
            effectiveness_detail_json=json.dumps(command["score_detail"], ensure_ascii=False),
        )
        try:
            result = customer_activity_write_service.create_final_from_assistant2(
                db, obj_in=obj_in, finalization=finalization,
                customer_id=customer_id, creator_id=str(task.user_id), team_id=team_id,
                actor_id=str(task.user_id),
            )
        except CustomerActivitySubmissionConflictError as exc:
            raise AssistantActivityCommitUnknownError() from exc
        except SQLAlchemyError as exc:
            db.rollback()
            try:
                existing = customer_activity_write_service.activity_crud.get_by_submission_id(
                    db, team_id=team_id, submission_id=submission_id
                )
            except SQLAlchemyError as readback_exc:
                raise AssistantActivityCommitUnknownError() from readback_exc
            if existing is not None:
                if (
                    existing.submission_fingerprint != expected_fingerprint
                    or existing.submission_source != "ASSISTANT_2"
                    or existing.customer_id is None
                    or int(existing.customer_id) != customer_id
                ):
                    raise AssistantActivityCommitUnknownError() from exc
                return WriteActivityResult(
                    True,
                    str(existing.id),
                    None,
                    customer_id,
                    follow_up_projection=None,
                )
            if isinstance(exc, DataError):
                raise AssistantStageFailure(
                    code=AssistantFailureCode.INTERNAL_ERROR,
                    stage="write",
                    retryable=False,
                    user_message="客户活动内容超出字段限制或格式不合法，本次没有写入客户活动，请修改后重试或联系管理员。",
                    task_public_id=task_public_id,
                ) from exc
            raise AssistantStageFailure(
                code=AssistantFailureCode.INTERNAL_ERROR,
                stage="write",
                retryable=True,
                user_message="数据库暂时繁忙，本次没有写入客户活动，请稍后重试。",
                task_public_id=task_public_id,
            ) from exc
        projection_receipt = None
        if result.follow_up_projection_job is not None:
            job = result.follow_up_projection_job
            raw_details = job.result_json
            details: dict[str, object] = raw_details if isinstance(raw_details, dict) else {}
            task_ids: list[int] = []
            for key in ("created_task_ids", "updated_task_ids"):
                raw_ids = details.get(key)
                if isinstance(raw_ids, list):
                    task_ids.extend(value for value in raw_ids if isinstance(value, int))
            public_task_ids = follow_up_task_crud.list_public_ids_by_ids(
                db, team_id=task.team_id, task_ids=task_ids
            )
            receipt_status = normalize_projection_status(str(job.status))
            raw_run_id = details.get("projection_run_id")
            raw_skip_reason = details.get("skip_reason")
            raw_error = details.get("error")
            projection_receipt = FollowUpProjectionReceipt(
                status=receipt_status,
                job_public_id=job.job_public_id,
                projection_run_id=raw_run_id if isinstance(raw_run_id, int) else None,
                task_public_id=public_task_ids[0] if public_task_ids else None,
                skip_reason=raw_skip_reason if isinstance(raw_skip_reason, str) else None,
                error_message=raw_error if isinstance(raw_error, str) else None,
            )
        return WriteActivityResult(
            True,
            str(result.activity.id),
            None,
            customer_id,
            projection_receipt,
        )
