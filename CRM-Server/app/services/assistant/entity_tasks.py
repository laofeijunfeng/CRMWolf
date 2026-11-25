"""Direct-create entity tasks: one task per CRM record (contact, invoice title, deployment, customer, opportunity).

The coordinator hands every non-activity task here; activity intake never sees entity tasks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.services.assistant.task_state import InvalidTaskTransitionError

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.assistant import AssistantTask
    from app.services.assistant.coordinator import AssistantInput, CoordinatorOutcome
    from app.services.assistant.events import ProgressReporter


async def handle_entity_task(
    db: Session, task: AssistantTask, user_input: AssistantInput, *, reporter: ProgressReporter
) -> CoordinatorOutcome:
    raise InvalidTaskTransitionError(f"{task.task_kind} intake is not wired yet")
