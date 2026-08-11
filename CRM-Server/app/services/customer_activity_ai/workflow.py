"""Persistent LangGraph workflow for customer activity AI processing."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.crud.customer_activity import customer_activity_crud
from app.models.customer import Contact, Customer
from app.models.customer_activity import CustomerActivity
from app.models.opportunity import Opportunity
from app.models.sales_commitment import FollowUpTaskProjectionTrigger
from app.services.customer_activity_ai.checkpointer import customer_activity_checkpoint_saver
from app.services.customer_activity_ai.evaluation_agent import (
    ActivityEvaluationAgent,
    ActivityEvaluationError,
    activity_evaluation_agent,
)
from app.services.customer_activity_ai.rules import get_activity_evaluation_rubric
from app.services.customer_activity_ai.schemas import CustomerActivityAIState
from app.services.customer_activity_ai.structuring_agent import (
    ActivityStructuringAgent,
    ActivityStructuringError,
    activity_structuring_agent,
)
from app.services.agent.temporal import agent_temporal_resolver
from app.services.customer_activity_kinds import get_activity_kind_meta
from app.services.customer_activity_post_commit_workflow import customer_activity_post_commit_workflow
from app.services.industry_display_service import industry_display_service

logger = logging.getLogger(__name__)


class CustomerActivityWorkflowError(Exception):
    """Raised when the customer activity workflow cannot complete."""


class CustomerActivityAIWorkflow:
    def __init__(
        self,
        *,
        structuring_agent: ActivityStructuringAgent | None = None,
        evaluation_agent: ActivityEvaluationAgent | None = None,
        checkpointer=customer_activity_checkpoint_saver,
    ) -> None:
        self.structuring_agent = structuring_agent or activity_structuring_agent
        self.evaluation_agent = evaluation_agent or activity_evaluation_agent
        self._graph = self._build_graph(checkpointer)

    def _build_graph(self, checkpointer):
        graph = StateGraph(CustomerActivityAIState)
        llm_retry = RetryPolicy(initial_interval=1.0, backoff_factor=2.0, max_interval=8.0, max_attempts=3)
        db_retry = RetryPolicy(initial_interval=0.2, backoff_factor=2.0, max_interval=2.0, max_attempts=3)

        graph.add_node("load_context", self._load_context, retry_policy=db_retry)
        graph.add_node("structure_activity", self._structure_activity, retry_policy=llm_retry)
        graph.add_node("persist_structured_content", self._persist_structured_content, retry_policy=db_retry)
        graph.add_node("evaluate_activity", self._evaluate_activity, retry_policy=llm_retry)
        graph.add_node("persist_evaluation_result", self._persist_evaluation_result, retry_policy=db_retry)

        graph.add_edge(START, "load_context")
        graph.add_conditional_edges(
            "load_context",
            self._route_after_load_context,
            {
                "structure": "structure_activity",
                "evaluate": "evaluate_activity",
            },
        )
        graph.add_edge("structure_activity", "persist_structured_content")
        graph.add_edge("persist_structured_content", "evaluate_activity")
        graph.add_edge("evaluate_activity", "persist_evaluation_result")
        graph.add_edge("persist_evaluation_result", END)
        return graph.compile(checkpointer=checkpointer)

    async def run(
        self,
        *,
        activity_id: int,
        team_id: int,
        mode: Literal["process", "evaluate"],
        run_id: str | None = None,
    ) -> CustomerActivityAIState:
        run_id = run_id or uuid4().hex
        thread_id = f"customer_activity:{activity_id}:{mode}:{run_id}"
        state: CustomerActivityAIState = {
            "activity_id": activity_id,
            "team_id": team_id,
            "run_id": run_id,
            "mode": mode,
            "events": [{"event": "workflow_started", "mode": mode, "run_id": run_id}],
        }
        return await self._graph.ainvoke(
            state,
            {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": "customer_activity_ai",
                },
                "metadata": {
                    "activity_id": activity_id,
                    "team_id": team_id,
                    "mode": mode,
                    "run_id": run_id,
                },
            },
        )

    def _route_after_load_context(self, state: CustomerActivityAIState) -> str:
        return "evaluate" if state.get("mode") == "evaluate" else "structure"

    def _load_context(self, state: CustomerActivityAIState) -> CustomerActivityAIState:
        db = SessionLocal()
        try:
            activity = customer_activity_crud.get_by_id(db, state["activity_id"], state["team_id"])
            if not activity:
                raise CustomerActivityWorkflowError("客户活动不存在")
            context = self._build_context(db, activity, state["team_id"])
            return {
                "context": context,
                "events": [{"event": "activity_context_loaded", "activity_id": activity.id}],
            }
        finally:
            db.close()

    async def _structure_activity(self, state: CustomerActivityAIState) -> CustomerActivityAIState:
        db = SessionLocal()
        try:
            result = await self.structuring_agent.structure(
                db,
                team_id=state["team_id"],
                context=state["context"],
            )
            return {
                "structure_result": result,
                "events": [{"event": "activity_structured"}],
            }
        except ActivityStructuringError:
            raise
        except Exception as exc:
            raise ActivityStructuringError(str(exc)) from exc
        finally:
            db.close()

    async def _persist_structured_content(self, state: CustomerActivityAIState) -> CustomerActivityAIState:
        result = state["structure_result"]
        db = SessionLocal()
        try:
            activity = customer_activity_crud.get_by_id(db, state["activity_id"], state["team_id"])
            if not activity:
                raise CustomerActivityWorkflowError("客户活动不存在")
            next_follow_time = self._resolve_structured_next_follow_time(result, activity)
            updated = customer_activity_crud.update_processed_content(
                db,
                state["activity_id"],
                title=result.get("title"),
                content_json=result.get("content_json") or {},
                summary=result.get("summary"),
                next_action=result.get("next_action"),
                next_follow_time=next_follow_time,
                next_follow_time_source="AI_EXTRACTED" if next_follow_time else None,
            )
            if not updated:
                raise CustomerActivityWorkflowError("客户活动不存在")
            customer_activity_crud.update_effectiveness_status(db, state["activity_id"], "GENERATING")
        finally:
            db.close()
        try:
            await customer_activity_post_commit_workflow.run(
                activity_id=state["activity_id"],
                team_id=state["team_id"],
                trigger_type=FollowUpTaskProjectionTrigger.ACTIVITY_STRUCTURED_COMPLETED,
                actor_id=None,
            )
        except Exception:
            logger.exception("客户活动结构化后 post-commit workflow 触发失败: activity_id=%s", state["activity_id"])

        db = SessionLocal()
        try:
            updated = customer_activity_crud.get_by_id(db, state["activity_id"], state["team_id"])
            if not updated:
                raise CustomerActivityWorkflowError("客户活动不存在")
            context = self._build_context(db, updated, state["team_id"])
            return {
                "context": context,
                "events": [{"event": "structured_content_persisted"}],
            }
        finally:
            db.close()

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

    def _persist_evaluation_result(self, state: CustomerActivityAIState) -> CustomerActivityAIState:
        result = state["evaluation_result"]
        db = SessionLocal()
        try:
            updated = customer_activity_crud.update_effectiveness_result(
                db,
                activity_id=state["activity_id"],
                score=int(result["score"]),
                is_valid=bool(result["is_valid"]),
                reason=str(result["reason"]),
                detail_json=json.dumps(result.get("principle_scores", {}), ensure_ascii=False),
            )
            if not updated:
                raise CustomerActivityWorkflowError("客户活动不存在")
            return {"events": [{"event": "evaluation_result_persisted"}]}
        finally:
            db.close()

    def _build_context(self, db: Session, activity: CustomerActivity, team_id: int) -> dict[str, Any]:
        customer = db.query(Customer).filter(Customer.id == activity.customer_id, Customer.team_id == team_id).first() if activity.customer_id else None
        contacts = db.query(Contact).filter(
            Contact.customer_id == activity.customer_id,
            Contact.team_id == team_id,
        ).order_by(Contact.is_primary.desc(), Contact.is_decision_maker.desc(), Contact.created_time.asc()).limit(20).all() if activity.customer_id else []
        opportunities = db.query(Opportunity).filter(
            Opportunity.customer_id == activity.customer_id,
            Opportunity.team_id == team_id,
        ).order_by(Opportunity.status.asc(), Opportunity.last_modified_time.desc()).limit(20).all() if activity.customer_id else []
        previous_activities = db.query(CustomerActivity).filter(
            CustomerActivity.customer_id == activity.customer_id,
            CustomerActivity.team_id == team_id,
            CustomerActivity.id != activity.id,
            CustomerActivity.occurred_at <= activity.occurred_at,
        ).order_by(CustomerActivity.occurred_at.desc()).limit(5).all() if activity.customer_id else []
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
            } if customer else None,
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
            "occurred_at": self._datetime(activity.occurred_at),
        }

    def _resolve_structured_next_follow_time(self, result: dict[str, Any], activity: CustomerActivity):
        if not self._can_ai_update_next_follow_time(activity):
            return None
        content_json = result.get("content_json") or {}
        if not isinstance(content_json, dict):
            return None
        next_follow_time_text = str(content_json.get("next_follow_time_text") or "").strip()
        if not next_follow_time_text:
            return None
        next_follow_time_iso = agent_temporal_resolver.resolve_follow_up_time_text(
            next_follow_time_text,
            base_datetime=activity.occurred_at,
        )
        return datetime.fromisoformat(next_follow_time_iso) if next_follow_time_iso else None

    def _can_ai_update_next_follow_time(self, activity: CustomerActivity) -> bool:
        source = activity.next_follow_time_source
        if source in {"USER", "AGENT", "MIGRATED"}:
            return False
        return activity.next_follow_time is None or source in {None, "UI_DEFAULT", "AI_EXTRACTED"}

    def _loads(self, value: str | None) -> dict[str, Any] | None:
        if not value:
            return None
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    def _datetime(self, value: datetime | None) -> str | None:
        return value.isoformat() if value else None


customer_activity_ai_workflow = CustomerActivityAIWorkflow()
