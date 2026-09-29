"""Write a frozen Assistant 2.0 activity and its receipt in the caller's transaction."""

from __future__ import annotations

from datetime import datetime
import json
from typing import TYPE_CHECKING

from app.crud.permission import permission_crud
from app.schemas.customer_activity import CustomerActivityCreate
from app.services.assistant.confirmation import WriteActivityResult, command_fingerprint
from app.services.customer_activity_access_policy import (
    CustomerActivityAccessDeniedError,
    CustomerActivityCustomerNotFoundError,
    customer_activity_access_policy,
)
from app.services.customer_activity_write_service import (
    CustomerActivityFinalization,
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

        next_action = command.get("next_action")
        content_json = command["content_json"]
        score = int(command["score"])
        obj_in = CustomerActivityCreate(
            activity_kind=str(command["activity_kind"]),
            title=str(command["title"]), summary=str(command["summary"]),
            source_content=str(command["source_content"]),
            content_json=content_json,
            next_action=str(next_action) if next_action else None,
            next_action_source="USER" if next_action else None,
            submission_source="ASSISTANT_2", submission_id=str(command["submission_id"]),
            submission_fingerprint=str(command["fingerprint"]),
        )
        finalization = CustomerActivityFinalization(
            title=obj_in.title, summary=obj_in.summary, content_json=content_json,
            next_action=obj_in.next_action, next_action_source=obj_in.next_action_source,
            next_follow_time=datetime.fromisoformat(str(command["next_follow_time"])) if command.get("next_follow_time") else None,
            next_follow_time_source="USER" if command.get("next_follow_time") else None,
            effectiveness_score=score, effectiveness_is_valid=score >= 60,
            effectiveness_reason=str(command["score_reason"]),
            effectiveness_detail_json=json.dumps(command["score_detail"], ensure_ascii=False),
        )
        result = customer_activity_write_service.create_final_from_assistant2(
            db, obj_in=obj_in, finalization=finalization,
            customer_id=int(customer.id), creator_id=str(task.user_id), team_id=task.team_id,
            actor_id=str(task.user_id),
        )
        return WriteActivityResult(True, str(result.activity.id), None, int(customer.id))
