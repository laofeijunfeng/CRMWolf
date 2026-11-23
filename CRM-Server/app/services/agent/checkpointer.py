"""LangGraph checkpointing primitives for the CRM Agent runtime."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.services.customer_activity_ai.checkpointer import SQLAlchemyCheckpointSaver

if TYPE_CHECKING:
    from sqlalchemy.exc import SQLAlchemyError

agent_checkpoint_saver = SQLAlchemyCheckpointSaver()


def is_checkpoint_storage_error(error: SQLAlchemyError) -> bool:
    traceback = error.__traceback__
    while traceback is not None:
        module = traceback.tb_frame.f_globals.get("__name__")
        if module == "app.services.customer_activity_ai.checkpointer":
            return True
        traceback = traceback.tb_next
    return False
