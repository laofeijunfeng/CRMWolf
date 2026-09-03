"""Pure-computation LangGraph workflow for customer-activity AI finalization."""

from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Protocol
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from app.core.database import SessionLocal
from app.crud.customer_activity import customer_activity_crud
from app.models.customer import Contact, Customer
from app.models.customer_activity import CustomerActivity
from app.models.opportunity import Opportunity
from app.services.agent.temporal import agent_temporal_resolver
from app.services.customer_activity_ai.checkpointer import customer_activity_checkpoint_saver
from app.services.customer_activity_ai.evaluation_agent import (
    ActivityEvaluationAgent,
    ActivityEvaluationError,
    activity_evaluation_agent,
)
from app.services.customer_activity_ai.rules import get_activity_evaluation_rubric
from app.services.customer_activity_ai.schemas import CustomerActivityAIFinalResult, CustomerActivityAIState
from app.services.customer_activity_ai.structuring_agent import (
    ActivityStructuringAgent,
    ActivityStructuringError,
    activity_structuring_agent,
)
from app.services.customer_activity_field_provenance import can_apply_ai_extracted_value
from app.services.customer_activity_kinds import get_activity_kind_meta
from app.services.industry_display_service import industry_display_service

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver
    from sqlalchemy.orm import Session


class _ActivityTemporalSnapshot(Protocol):
    next_follow_time: datetime | None
    next_follow_time_source: str | None
    occurred_at: datetime | None


class CustomerActivityWorkflowError(Exception):
    """Raised when the customer activity workflow cannot compute a final result."""


class CustomerActivityAIWorkflow:
    """Compute one structured draft and score without writing business state."""

    def __init__(
        self,
        *,
        structuring_agent: ActivityStructuringAgent | None = None,
        evaluation_agent: ActivityEvaluationAgent | None = None,
        checkpointer: BaseCheckpointSaver = customer_activity_checkpoint_saver,
    ) -> None:
        self.structuring_agent = structuring_agent or activity_structuring_agent
        self.evaluation_agent = evaluation_agent or activity_evaluation_agent
        self._graph = self._build_graph(checkpointer)

    def _build_graph(self, checkpointer: BaseCheckpointSaver):  # noqa: ANN202
        graph = StateGraph(CustomerActivityAIState)
        llm_retry = RetryPolicy(initial_interval=1.0, backoff_factor=2.0, max_interval=8.0, max_attempts=3)
        db_retry = RetryPolicy(initial_interval=0.2, backoff_factor=2.0, max_interval=2.0, max_attempts=3)
        graph.add_node("load_context", self._load_context, retry_policy=db_retry)
        graph.add_node("structure_activity", self._structure_activity, retry_policy=llm_retry)
        graph.add_node("prepare_evaluation_context", self._prepare_evaluation_context)
        graph.add_node("evaluate_activity", self._evaluate_activity, retry_policy=llm_retry)
        graph.add_edge(START, "load_context")
        graph.add_edge("load_context", "structure_activity")
        graph.add_edge("structure_activity", "prepare_evaluation_context")
        graph.add_edge("prepare_evaluation_context", "evaluate_activity")
        graph.add_edge("evaluate_activity", END)
        return graph.compile(checkpointer=checkpointer)

    async def run(
        self,
        *,
        activity_id: int,
        team_id: int,
        run_id: str | None = None,
        thread_id: str | None = None,
        expected_activity_revision: int | None = None,
    ) -> CustomerActivityAIState:
        resolved_run_id = run_id or uuid4().hex
        resolved_thread_id = thread_id or f"customer_activity:{activity_id}:{resolved_run_id}"
        state: CustomerActivityAIState = {
            "activity_id": activity_id,
            "team_id": team_id,
            "run_id": resolved_run_id,
            "expected_activity_revision": expected_activity_revision,
            "events": [{"event": "workflow_started", "run_id": resolved_run_id}],
        }
        return await self._graph.ainvoke(
            state,
            {
                "configurable": {"thread_id": resolved_thread_id, "checkpoint_ns": "customer_activity_ai"},
                "metadata": {
                    "activity_id": activity_id,
                    "team_id": team_id,
                            "run_id": resolved_run_id,
                    "activity_revision": expected_activity_revision,
                },
            },
        )

    async def compute_finalization(
        self,
        *,
        activity_id: int,
        team_id: int,
        expected_activity_revision: int,
        run_id: str,
        thread_id: str,
    ) -> CustomerActivityAIFinalResult:
        state = await self.run(
            activity_id=activity_id,
            team_id=team_id,
            run_id=run_id,
            thread_id=thread_id,
            expected_activity_revision=expected_activity_revision,
        )
        structure = state.get("structure_result") or {}
        evaluation = state.get("evaluation_result") or {}
        original = (state.get("original_context") or state.get("context") or {}).get("current_activity") or {}
        next_follow_time = self._resolve_structured_next_follow_time(
            structure,
            SimpleNamespace(
                next_follow_time=self._parse_datetime(original.get("next_follow_time")),
                next_follow_time_source=original.get("next_follow_time_source"),
                occurred_at=self._parse_datetime(original.get("occurred_at")),
            ),
        )
        next_action = structure.get("next_action")
        next_action_source = "AI_EXTRACTED" if next_action else None
        if next_action is not None and not can_apply_ai_extracted_value(
            current_value=original.get("next_action"),
            current_source=original.get("next_action_source"),
        ):
            next_action = None
            next_action_source = None
        content_json = structure.get("content_json") or {}
        if not isinstance(content_json, dict):
            raise CustomerActivityWorkflowError("客户活动整理结果格式无效")
        return CustomerActivityAIFinalResult(
            title=structure.get("title"),
            content_json=content_json,
            summary=structure.get("summary"),
            next_action=next_action,
            next_action_source=next_action_source,
            next_follow_time=next_follow_time,
            next_follow_time_source="AI_EXTRACTED" if next_follow_time else None,
            effectiveness_score=int(evaluation["score"]),
            effectiveness_is_valid=bool(evaluation["is_valid"]),
            effectiveness_reason=str(evaluation["reason"]),
            effectiveness_detail=evaluation.get("principle_scores") or {},
        )

    def _load_context(self, state: CustomerActivityAIState) -> CustomerActivityAIState:
        db = SessionLocal()
        try:
            activity = customer_activity_crud.get_by_id(db, state["activity_id"], state["team_id"])
            if not activity:
                raise CustomerActivityWorkflowError("客户活动不存在")
            expected_revision = state.get("expected_activity_revision")
            if expected_revision is not None and int(activity.activity_revision or 1) != expected_revision:
                raise CustomerActivityWorkflowError("客户活动修订号已变化")
            context = self._build_context(db, activity, state["team_id"])
            return {
                "context": context,
                "original_context": context,
                "events": [{"event": "activity_context_loaded", "activity_id": activity.id}],
            }
        finally:
            db.close()

    async def _structure_activity(self, state: CustomerActivityAIState) -> CustomerActivityAIState:
        db = SessionLocal()
        try:
            result = await self.structuring_agent.structure(db, team_id=state["team_id"], context=state["context"])
            return {"structure_result": result, "events": [{"event": "activity_structured"}]}
        except ActivityStructuringError:
            raise
        except Exception as exc:
            raise ActivityStructuringError(str(exc)) from exc
        finally:
            db.close()

    @staticmethod
    def _prepare_evaluation_context(state: CustomerActivityAIState) -> CustomerActivityAIState:
        context = state["context"]
        structure = state["structure_result"]
        current = context["current_activity"]
        evaluated_context = {
            **context,
            "current_activity": {
                **current,
                "title": structure.get("title"),
                "content_json": structure.get("content_json") or {},
                "summary": structure.get("summary"),
                "next_action": structure.get("next_action"),
            },
        }
        return {"context": evaluated_context, "events": [{"event": "evaluation_context_prepared"}]}

    async def _evaluate_activity(self, state: CustomerActivityAIState) -> CustomerActivityAIState:
        context = state["context"]
        meta = get_activity_kind_meta(context["current_activity"]["activity_kind"])
        rubric = get_activity_evaluation_rubric(meta.get("score_rule"))
        db = SessionLocal()
        try:
            result = await self.evaluation_agent.evaluate(
                db,
                team_id=state["team_id"],
                context=context,
                rubric=rubric,
            )
            return {
                "evaluation_result": result,
                "events": [{"event": "activity_evaluated", "score": result.get("score")}],
            }
        except ActivityEvaluationError:
            raise
        except Exception as exc:
            raise ActivityEvaluationError(str(exc)) from exc
        finally:
            db.close()

    def _build_context(self, db: Session, activity: CustomerActivity, team_id: int) -> dict[str, Any]:
        customer = (
            db.query(Customer).filter(Customer.id == activity.customer_id, Customer.team_id == team_id).first()
            if activity.customer_id
            else None
        )
        contacts = (
            db.query(Contact)
            .filter(Contact.customer_id == activity.customer_id, Contact.team_id == team_id)
            .order_by(Contact.is_primary.desc(), Contact.is_decision_maker.desc(), Contact.created_time.asc())
            .limit(20)
            .all()
            if activity.customer_id
            else []
        )
        opportunities = (
            db.query(Opportunity)
            .filter(Opportunity.customer_id == activity.customer_id, Opportunity.team_id == team_id)
            .order_by(Opportunity.status.asc(), Opportunity.last_modified_time.desc())
            .limit(20)
            .all()
            if activity.customer_id
            else []
        )
        previous_activities = (
            db.query(CustomerActivity)
            .filter(
                CustomerActivity.customer_id == activity.customer_id,
                CustomerActivity.team_id == team_id,
                CustomerActivity.id != activity.id,
                CustomerActivity.occurred_at <= activity.occurred_at,
            )
            .order_by(CustomerActivity.occurred_at.desc())
            .limit(5)
            .all()
            if activity.customer_id
            else []
        )
        return {
            "current_activity": self._activity_to_dict(activity),
            "customer": {
                "id": customer.public_id,
                "public_id": customer.public_id,
                "account_name": customer.account_name,
                "industry_code": customer.industry,
                "industry_name": industry_display_service.display_name(db, customer.industry),
                "city": customer.city,
                "company_scale": customer.company_scale,
                "source": customer.source,
            }
            if customer
            else None,
            "contacts": [
                {
                    "name": contact.name,
                    "position": contact.position,
                    "mobile": contact.mobile,
                    "email": contact.email,
                    "is_primary": bool(contact.is_primary),
                    "is_decision_maker": bool(contact.is_decision_maker),
                    "remark": contact.remark,
                }
                for contact in contacts
            ],
            "opportunities": [
                {
                    "id": opportunity.id,
                    "name": opportunity.opportunity_name,
                    "stage": opportunity.current_stage_name,
                    "win_probability": opportunity.current_win_probability,
                    "amount": float(opportunity.total_amount) if opportunity.total_amount is not None else None,
                    "status": opportunity.status,
                }
                for opportunity in opportunities
            ],
            "previous_activities": [self._activity_to_dict(item) for item in reversed(previous_activities)],
        }

    def _activity_to_dict(self, activity: CustomerActivity) -> dict[str, Any]:
        meta = get_activity_kind_meta(activity.activity_kind)
        return {
            "id": activity.id,
            "activity_revision": int(activity.activity_revision or 1),
            "activity_kind": activity.activity_kind,
            "activity_category": meta["category"],
            "activity_label": meta["label"],
            "score_rule": meta["score_rule"],
            "title": activity.title,
            "source_content": activity.source_content,
            "content_json": self._loads(activity.content_json),
            "summary": activity.summary,
            "next_follow_time": self._datetime(activity.next_follow_time),
            "next_follow_time_source": activity.next_follow_time_source,
            "next_action": activity.next_action,
            "next_action_source": getattr(activity, "next_action_source", None),
            "occurred_at": self._datetime(activity.occurred_at),
        }

    def _resolve_structured_next_follow_time(
        self,
        result: dict[str, Any],
        activity: _ActivityTemporalSnapshot,
    ) -> datetime | None:
        if not can_apply_ai_extracted_value(
            current_value=activity.next_follow_time,
            current_source=activity.next_follow_time_source,
        ):
            return None
        content_json = result.get("content_json") or {}
        if not isinstance(content_json, dict):
            return None
        text = str(content_json.get("next_follow_time_text") or "").strip()
        if not text or activity.occurred_at is None:
            return None
        resolved = agent_temporal_resolver.resolve_follow_up_time_text(text, base_datetime=activity.occurred_at)
        return datetime.fromisoformat(resolved) if resolved else None

    @staticmethod
    def _loads(value: str | None) -> dict[str, Any] | None:
        if not value:
            return None
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    @staticmethod
    def _datetime(value: datetime | None) -> str | None:
        return value.isoformat() if value else None

    @staticmethod
    def _parse_datetime(value: object) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str) and value:
            return datetime.fromisoformat(value)
        return None


customer_activity_ai_workflow = CustomerActivityAIWorkflow()
