from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.crud.permission import permission_crud
from app.crud.sales_commitment import follow_up_task_crud
from app.models.customer import Customer, CustomerMember
from app.models.customer_activity import CustomerActivity
from app.models.sales_commitment import FollowUpTask, FollowUpTaskStatus
from app.services.follow_up_task_semantic_evidence_service import (
    FollowUpTaskSemanticEvidenceService,
    follow_up_task_semantic_evidence_service,
)
from app.services.work_summary_service import work_summary_service
from app.utils.time import (
    FOLLOW_UP_TASK_DUE_WINDOW_OVERDUE,
    business_now,
    calculate_follow_up_task_due_window,
)

FOLLOW_UP_TASK_QUERY_STATUSES = {
    "open": [FollowUpTaskStatus.OPEN],
    "completed": [FollowUpTaskStatus.COMPLETED],
    "cancelled": [FollowUpTaskStatus.CANCELLED],
    "all": None,
}
FOLLOW_UP_TASK_OWNER_SCOPES = {"mine", "customer"}


class FollowUpTaskQueryService:
    def __init__(
        self,
        *,
        semantic_evidence_service: FollowUpTaskSemanticEvidenceService | None = None,
    ) -> None:
        self.semantic_evidence_service = semantic_evidence_service or follow_up_task_semantic_evidence_service

    def list_tasks(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        status: str = "open",
        due_window: str | None = None,
        customer_public_id: str | None = None,
        owner_scope: str = "mine",
        query_text: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        statuses = self._normalize_status(status)
        customer = self._resolve_visible_customer(db, team_id=team_id, user_id=user_id, public_id=customer_public_id)
        if owner_scope not in FOLLOW_UP_TASK_OWNER_SCOPES:
            raise ValueError("未知任务归属范围")
        if owner_scope == "customer" and customer is None:
            raise ValueError("customer 范围查询必须提供 customer_id")

        semantic_evidence_by_task_id: dict[str, list[dict[str, Any]]] = {}
        semantic_retrieval = self._semantic_retrieval_not_attempted()
        semantic_task_public_ids: list[str] | None = None
        clean_query_text = query_text.strip() if isinstance(query_text, str) else ""
        if clean_query_text:
            semantic_result = self.semantic_evidence_service.recall(
                db,
                team_id=team_id,
                query_text=clean_query_text,
                limit=limit,
            )
            semantic_retrieval = semantic_result.retrieval_event
            semantic_evidence_by_task_id = semantic_result.evidence_by_task_public_id
            semantic_task_public_ids = semantic_result.task_public_ids

        rows, total = self._list_filtered_tasks(
            db,
            team_id=team_id,
            user_id=user_id,
            statuses=statuses,
            due_window=due_window,
            customer_id=customer.id if customer is not None else None,
            owner_scope=owner_scope,
            limit=limit,
            semantic_task_public_ids=semantic_task_public_ids,
        )

        customers_by_id = self._customers_by_id(db, team_id=team_id, customer_ids=[task.customer_id for task in rows])
        items = [
            self._task_payload(
                task,
                customers_by_id.get(task.customer_id),
                semantic_evidence=semantic_evidence_by_task_id.get(str(task.public_id)),
            )
            for task in rows
        ]
        return {
            "items": items,
            "total": total,
            "filters": {
                "status": status,
                "due_window": due_window,
                "customer_id": customer.public_id if customer else None,
                "owner_scope": owner_scope,
                "query_text": clean_query_text or None,
            },
            "customer_summary": self._customer_summary(items),
            "semantic_retrieval": semantic_retrieval,
            "usage_policy": {
                "task_state_source": "mysql",
                "semantic_evidence_source": "qdrant",
                "rule": "任务状态、归属和权限以结构化任务表为准；向量库只提供语义候选和解释证据。",
            },
        }

    def get_task_detail(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        task_public_id: str,
    ) -> dict[str, Any]:
        task = follow_up_task_crud.get_by_public_id(db, task_public_id, team_id)
        if task is None:
            raise ValueError("任务不存在")
        customer = db.query(Customer).filter(Customer.team_id == team_id, Customer.id == task.customer_id).first()
        if task.owner_id != str(user_id) and not self._can_view_customer(db, team_id=team_id, user_id=user_id, customer=customer):
            raise PermissionError("无权查看该任务")
        activity = None
        if task.source_activity_id is not None:
            activity = (
                db.query(CustomerActivity)
                .filter(CustomerActivity.team_id == team_id, CustomerActivity.id == task.source_activity_id)
                .first()
            )
        payload = self._task_payload(task, customer)
        payload["source_activity"] = self._activity_payload(activity)
        return payload

    def list_completed_work(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        window: str = "this_week",
        customer_public_id: str | None = None,
        start_at: str | None = None,
        end_at: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        return work_summary_service.list_completed_work(
            db,
            team_id=team_id,
            user_id=user_id,
            window=window,
            customer_public_id=customer_public_id,
            include_tasks=True,
            include_activities=True,
            include_business_events=False,
            start_at=start_at,
            end_at=end_at,
            cursor=cursor,
            limit=limit,
        )

    def _normalize_status(self, status: str) -> list[str] | None:
        if status not in FOLLOW_UP_TASK_QUERY_STATUSES:
            raise ValueError("未知任务状态过滤")
        return FOLLOW_UP_TASK_QUERY_STATUSES[status]

    def _list_filtered_tasks(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        statuses: list[str] | None,
        due_window: str | None,
        customer_id: int | None,
        owner_scope: str,
        limit: int,
        semantic_task_public_ids: list[str] | None,
    ) -> tuple[list[FollowUpTask], int]:
        if semantic_task_public_ids == []:
            return [], 0

        if semantic_task_public_ids is None:
            if owner_scope == "customer":
                return follow_up_task_crud.list_for_customer(
                    db,
                    team_id=team_id,
                    customer_id=customer_id,
                    statuses=statuses,
                    due_window=due_window,
                    limit=limit,
                )
            return follow_up_task_crud.list_for_owner(
                db,
                team_id=team_id,
                owner_id=str(user_id),
                statuses=statuses,
                due_window=due_window,
                customer_id=customer_id,
                limit=limit,
            )

        query = db.query(FollowUpTask).filter(
            FollowUpTask.team_id == team_id,
            FollowUpTask.public_id.in_(semantic_task_public_ids),
        )
        if statuses is not None:
            query = query.filter(FollowUpTask.status.in_(statuses))
        if owner_scope == "customer":
            query = query.filter(FollowUpTask.customer_id == customer_id)
        else:
            query = query.filter(FollowUpTask.owner_id == str(user_id))
            if customer_id is not None:
                query = query.filter(FollowUpTask.customer_id == customer_id)
        query = follow_up_task_crud._apply_task_filters(
            query,
            statuses=None,
            due_window=due_window,
        )
        rows = query.all()
        rank_by_public_id = {task_public_id: index for index, task_public_id in enumerate(semantic_task_public_ids)}
        sorted_rows = sorted(
            rows,
            key=lambda task: (rank_by_public_id.get(str(task.public_id), len(rank_by_public_id)), task.due_at, task.id),
        )
        return sorted_rows[:limit], len(sorted_rows)

    @staticmethod
    def _semantic_retrieval_not_attempted() -> dict[str, Any]:
        return {
            "event": "follow_up_task_semantic_evidence",
            "status": "not_attempted",
            "candidate_task_count": 0,
        }

    def _resolve_visible_customer(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        public_id: str | None,
    ) -> Customer | None:
        if public_id is None:
            return None
        customer = db.query(Customer).filter(Customer.team_id == team_id, Customer.public_id == public_id).first()
        if customer is None:
            raise ValueError("客户不存在")
        if not self._can_view_customer(db, team_id=team_id, user_id=user_id, customer=customer):
            raise PermissionError("无权查看该客户")
        return customer

    def _can_view_customer(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        customer: Customer | None,
    ) -> bool:
        if customer is None:
            return False
        permission_codes = {permission.code for permission in permission_crud.get_user_permissions(db, user_id, team_id)}
        user_id_text = str(user_id)
        if "customer:view:all" in permission_codes:
            return True
        if "customer:view:own" in permission_codes and customer.owner_id == user_id_text:
            return True
        return db.query(CustomerMember.id).filter(
            CustomerMember.team_id == team_id,
            CustomerMember.customer_id == customer.id,
            CustomerMember.user_id == user_id_text,
            CustomerMember.is_active.is_(True),
        ).first() is not None

    def _customers_by_id(self, db: Session, *, team_id: int, customer_ids: list[int]) -> dict[int, Customer]:
        ids = list(dict.fromkeys(customer_id for customer_id in customer_ids if customer_id))
        if not ids:
            return {}
        rows = db.query(Customer).filter(Customer.team_id == team_id, Customer.id.in_(ids)).all()
        return {customer.id: customer for customer in rows}

    def _task_payload(
        self,
        task: FollowUpTask,
        customer: Customer | None,
        *,
        semantic_evidence: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return {
            "id": task.public_id,
            "public_id": task.public_id,
            "customer": self._customer_payload(customer),
            "owner_id": task.owner_id,
            "creator_id": task.creator_id,
            "title": task.title,
            "description": task.description,
            "status": task.status,
            "due_at": task.due_at.isoformat() if task.due_at else None,
            "due_at_text": task.due_at_text,
            "due_at_granularity": task.due_at_granularity,
            "due_at_timezone": task.due_at_timezone,
            "overdue_days": self._overdue_days(task),
            "source_type": task.source_type,
            "source_public_id": task.source_public_id,
            "confidence": task.confidence,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "cancelled_at": task.cancelled_at.isoformat() if task.cancelled_at else None,
            "created_time": task.created_time.isoformat() if task.created_time else None,
            "updated_time": task.updated_time.isoformat() if task.updated_time else None,
            "semantic_evidence": semantic_evidence or [],
        }

    def _activity_payload(
        self,
        activity: CustomerActivity | None,
        customer: Customer | None = None,
    ) -> dict[str, Any] | None:
        if activity is None:
            return None
        return {
            "customer": self._customer_payload(customer),
            "activity_kind": activity.activity_kind,
            "title": activity.title,
            "summary": activity.summary,
            "next_action": activity.next_action,
            "next_follow_time": activity.next_follow_time.isoformat() if activity.next_follow_time else None,
            "occurred_at": activity.occurred_at.isoformat() if activity.occurred_at else None,
            "owner_id": activity.owner_id,
        }

    @staticmethod
    def _customer_payload(customer: Customer | None) -> dict[str, Any] | None:
        if customer is None:
            return None
        return {
            "id": customer.public_id,
            "public_id": customer.public_id,
            "name": customer.account_name,
            "account_name": customer.account_name,
        }

    @staticmethod
    def _customer_summary(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        summary_by_customer: dict[str, dict[str, Any]] = {}
        for item in items:
            customer = item.get("customer")
            if not isinstance(customer, dict):
                continue
            customer_id = str(customer.get("id") or "")
            if not customer_id:
                continue
            summary = summary_by_customer.setdefault(
                customer_id,
                {
                    "customer": customer,
                    "open_task_count": 0,
                    "overdue_task_count": 0,
                    "nearest_due_at": None,
                },
            )
            if item.get("status") == FollowUpTaskStatus.OPEN:
                summary["open_task_count"] += 1
            if int(item.get("overdue_days") or 0) > 0:
                summary["overdue_task_count"] += 1
            due_at = item.get("due_at")
            if due_at and (summary["nearest_due_at"] is None or str(due_at) < str(summary["nearest_due_at"])):
                summary["nearest_due_at"] = due_at
        return list(summary_by_customer.values())

    @staticmethod
    def _overdue_days(task: FollowUpTask) -> int:
        if task.status != FollowUpTaskStatus.OPEN or task.due_at is None:
            return 0
        now = business_now()
        overdue_window = calculate_follow_up_task_due_window(FOLLOW_UP_TASK_DUE_WINDOW_OVERDUE, now=now)
        if task.due_at >= overdue_window.ends_at and task.due_at >= now:
            return 0
        return max(0, (now.date() - task.due_at.date()).days)


follow_up_task_query_service = FollowUpTaskQueryService()
