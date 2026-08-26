"""Late binding and recovery for CRM durable work owned by Agent turns."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pydantic import TypeAdapter, ValidationError

from app.crud.customer_activity_post_commit_job import customer_activity_post_commit_job_crud
from app.services.agent.async_operation_service import (
    AgentAsyncOperationService,
    agent_async_operation_service,
)
from app.services.agent.durable_work_contracts import (
    AgentAsyncOperationBinding,
    AgentDurableWorkReceipt,
    CustomerActivityDurableWorkReceipt,
)
from app.services.agent.turns import AgentTurnRepository
from app.services.customer_activity_agent_origin_service import (
    CustomerActivityAgentOriginService,
    customer_activity_agent_origin_service,
)
from app.services.customer_activity_post_commit_operation_projector import (
    CustomerActivityPostCommitOperationProjector,
    customer_activity_post_commit_operation_projector,
)
from app.services.customer_intelligence_refresh_service import (
    CustomerIntelligenceRefreshService,
    customer_intelligence_refresh_service,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)
_DURABLE_WORK_ADAPTER: TypeAdapter[list[AgentDurableWorkReceipt]] = TypeAdapter(
    list[AgentDurableWorkReceipt]
)


class AgentDurableWorkBinder:
    """Bind committed work to its exact Agent turn after the message commit."""

    def __init__(
        self,
        *,
        operation_service: AgentAsyncOperationService | None = None,
        post_commit_projector: CustomerActivityPostCommitOperationProjector | None = None,
        intelligence_service: CustomerIntelligenceRefreshService | None = None,
        activity_origin_service: CustomerActivityAgentOriginService | None = None,
    ) -> None:
        self.operation_service = operation_service or agent_async_operation_service
        self.post_commit_projector = (
            post_commit_projector or customer_activity_post_commit_operation_projector
        )
        self.intelligence_service = intelligence_service or customer_intelligence_refresh_service
        self.activity_origin_service = activity_origin_service or customer_activity_agent_origin_service

    def bind(
        self,
        db: Session,
        *,
        receipts: list[AgentDurableWorkReceipt] | tuple[AgentDurableWorkReceipt, ...],
        binding: AgentAsyncOperationBinding,
    ) -> None:
        """Bind de-duplicated receipts inside the caller-owned short transaction."""

        seen: set[tuple[str, int, str | None, str | None]] = set()
        for receipt in receipts:
            if not isinstance(receipt, CustomerActivityDurableWorkReceipt):
                raise TypeError("unsupported Agent durable-work receipt")
            identity = (
                receipt.type,
                receipt.activity_id,
                receipt.post_commit_job_public_id,
                receipt.customer_intelligence_request_id,
            )
            if identity in seen:
                continue
            seen.add(identity)
            self._bind_customer_activity(db, receipt=receipt, binding=binding)

    def _bind_customer_activity(
        self,
        db: Session,
        *,
        receipt: CustomerActivityDurableWorkReceipt,
        binding: AgentAsyncOperationBinding,
    ) -> None:
        job = customer_activity_post_commit_job_crud.get_by_public_id(
            db,
            team_id=binding.team_id,
            public_id=receipt.post_commit_job_public_id,
        )
        if job is None:
            raise ValueError("客户活动后提交任务不存在")
        if int(job.activity_id) != receipt.activity_id:
            raise ValueError("客户活动后提交任务与回执不匹配")
        operation = self.operation_service.bind_source(
            db,
            operation_key=f"customer-activity-post-commit:{receipt.post_commit_job_public_id}",
            request_id=receipt.post_commit_job_public_id,
            team_id=binding.team_id,
            user_id=binding.user_id,
            session_id=binding.session_id,
            source_user_message_id=binding.source_user_message_id,
            source_assistant_message_id=binding.source_assistant_message_id,
            operation_type="customer_activity_post_commit",
            resource_type="customer_activity",
            resource_id=receipt.activity_id,
            graph_thread_id=str(job.graph_thread_id) if job.graph_thread_id else None,
            summary="跟进已记录,任务对账处理中",
        )
        projected = self.post_commit_projector.project_job(
            db,
            job,
            operation_public_id=str(operation.public_id),
        )
        if projected is None:
            raise RuntimeError("客户活动后提交异步操作绑定后投影不可见")
        origin = self.activity_origin_service.ensure_from_bound_operation(
            db,
            operation=operation,
        )
        if origin is None:
            raise RuntimeError("客户活动无法绑定到来源 Agent 轮次")

        self.intelligence_service.bind_committed_event_to_agent(
            db,
            team_id=binding.team_id,
            request_id=receipt.customer_intelligence_request_id,
            binding=binding,
        )


class AgentDurableWorkRecoveryService:
    """Recover missing Agent operation projections from committed assistant receipts.

    The assistant message diagnostics are the sole recovery source. This does not
    re-run CRM writes or introduce a second producer path; it only repeats the
    idempotent late binding that should have followed the committed turn.
    """

    def __init__(
        self,
        *,
        binder: AgentDurableWorkBinder | None = None,
        turn_repository: AgentTurnRepository | None = None,
        operation_service: AgentAsyncOperationService | None = None,
    ) -> None:
        self.binder = binder or agent_durable_work_binder
        self.turn_repository = turn_repository or AgentTurnRepository()
        self.operation_service = operation_service or self.binder.operation_service

    def recover_session(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        session_id: int,
    ) -> int:
        assistant_messages = self.turn_repository.list_assistant_messages_with_diagnostics(
            db,
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
        )
        receipts_by_message = []
        for message in assistant_messages:
            diagnostics = message.diagnostics
            raw_receipts = diagnostics.get("durable_work") if isinstance(diagnostics, dict) else None
            if not isinstance(raw_receipts, list) or not raw_receipts:
                continue
            try:
                receipts = _DURABLE_WORK_ADAPTER.validate_python(raw_receipts)
            except ValidationError:
                logger.warning(
                    "Skipping invalid Agent durable-work receipt: assistant_message_id=%s",
                    message.id,
                )
                continue
            receipts_by_message.append((message, receipts))

        if not receipts_by_message:
            return 0

        turn_ids = {message.turn_id for message, _ in receipts_by_message}
        user_messages = self.turn_repository.list_user_messages_by_turn_ids(
            db,
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
            turn_ids=turn_ids,
        )
        user_message_by_turn = {message.turn_id: message for message in user_messages}

        recovered = 0
        for assistant_message, receipts in receipts_by_message:
            user_message = user_message_by_turn.get(str(assistant_message.turn_id))
            if user_message is None:
                logger.warning(
                    "Skipping Agent durable-work receipt without owned user turn: assistant_message_id=%s",
                    assistant_message.id,
                )
                continue
            binding = AgentAsyncOperationBinding(
                team_id=team_id,
                user_id=user_id,
                session_id=session_id,
                source_user_message_id=int(user_message.id),
                source_assistant_message_id=int(assistant_message.id),
            )
            pending_receipts = [
                receipt
                for receipt in receipts
                if self._receipt_needs_binding(db, receipt=receipt, binding=binding)
            ]
            if not pending_receipts:
                continue
            self.binder.bind(db, receipts=pending_receipts, binding=binding)
            recovered += len(pending_receipts)
        return recovered

    def _receipt_needs_binding(
        self,
        db: Session,
        *,
        receipt: AgentDurableWorkReceipt,
        binding: AgentAsyncOperationBinding,
    ) -> bool:
        if not isinstance(receipt, CustomerActivityDurableWorkReceipt):
            raise TypeError("unsupported Agent durable-work receipt")
        operation_keys = [
            f"customer-activity-post-commit:{receipt.post_commit_job_public_id}",
            f"customer-intelligence:{receipt.customer_intelligence_request_id}",
        ]
        operations = self.operation_service.list_by_operation_keys(
            db,
            team_id=binding.team_id,
            operation_keys=set(operation_keys),
        )
        by_key = {operation.operation_key: operation for operation in operations}
        for operation_key in operation_keys:
            operation = by_key.get(operation_key)
            if operation is None:
                return True
            if (
                int(operation.user_id) != binding.user_id
                or operation.session_id is None
                or int(operation.session_id) != binding.session_id
                or operation.source_user_message_id is None
                or int(operation.source_user_message_id) != binding.source_user_message_id
                or operation.source_assistant_message_id is None
                or int(operation.source_assistant_message_id) != binding.source_assistant_message_id
            ):
                return True
        return False


agent_durable_work_binder = AgentDurableWorkBinder()
agent_durable_work_recovery_service = AgentDurableWorkRecoveryService(
    binder=agent_durable_work_binder
)
