"""Async entrypoint for customer activity AI workflows."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from app.core.database import SessionLocal
from app.crud.customer_activity import customer_activity_crud
from app.services.ai_task_limiter import ai_generation_semaphore
from app.services.customer_activity_ai.evaluation_agent import ActivityEvaluationError
from app.services.customer_activity_ai.structuring_agent import ActivityStructuringError
from app.services.customer_activity_ai.workflow import customer_activity_ai_workflow
from app.services.customer_activity_post_commit_workflow import customer_activity_post_commit_workflow

logger = logging.getLogger(__name__)


def _empty_post_commit_outcome() -> Dict[str, Any]:
    return {
        "needs_user_confirmation": False,
        "confirmation_case_public_ids": [],
        "confirmation_cases": [],
        "created_confirmation_case_count": 0,
        "prompt_policy": {
            "prompt_scope": "current_activity",
            "delivery": "channel_contextual",
        },
    }


class CustomerActivityProcessingService:
    async def process(self, activity_id: int, team_id: int) -> Dict[str, Any]:
        logger.info("开始客户活动 AI workflow: activity_id=%s, team_id=%s, mode=process", activity_id, team_id)
        async with ai_generation_semaphore:
            try:
                db = SessionLocal()
                try:
                    customer_activity_crud.update_processing_status(db, activity_id, "PROCESSING")
                finally:
                    db.close()
                await customer_activity_ai_workflow.run(activity_id=activity_id, team_id=team_id, mode="process")
                logger.info("客户活动 AI workflow 完成: activity_id=%s, mode=process", activity_id)
                return {"success": True, "activity_id": activity_id}
            except ActivityStructuringError as exc:
                logger.exception("客户活动整理失败: activity_id=%s", activity_id)
                self._mark_processing_failed(activity_id, str(exc))
                return {"success": False, "activity_id": activity_id, "error": str(exc)}
            except ActivityEvaluationError as exc:
                logger.exception("客户活动评分失败: activity_id=%s", activity_id)
                self._mark_evaluation_failed(activity_id, str(exc))
                return {"success": False, "activity_id": activity_id, "error": str(exc)}
            except Exception as exc:
                logger.exception("客户活动 AI workflow 失败: activity_id=%s", activity_id)
                self._mark_processing_failed(activity_id, str(exc))
                return {"success": False, "activity_id": activity_id, "error": str(exc)}

    async def evaluate(self, activity_id: int, team_id: int) -> Dict[str, Any]:
        logger.info("开始客户活动 AI workflow: activity_id=%s, team_id=%s, mode=evaluate", activity_id, team_id)
        async with ai_generation_semaphore:
            try:
                db = SessionLocal()
                try:
                    customer_activity_crud.update_effectiveness_status(db, activity_id, "GENERATING")
                finally:
                    db.close()
                state = await customer_activity_ai_workflow.run(activity_id=activity_id, team_id=team_id, mode="evaluate")
                result = state.get("evaluation_result") or {}
                return {"success": True, "activity_id": activity_id, "score": result.get("score")}
            except ActivityEvaluationError as exc:
                logger.exception("客户活动有效性评估失败: activity_id=%s", activity_id)
                self._mark_evaluation_failed(activity_id, str(exc))
                return {"success": False, "activity_id": activity_id, "error": str(exc)}
            except Exception as exc:
                logger.exception("客户活动有效性评估失败: activity_id=%s", activity_id)
                self._mark_evaluation_failed(activity_id, str(exc))
                return {"success": False, "activity_id": activity_id, "error": str(exc)}

    async def trigger_processing(self, activity_id: int, team_id: int) -> None:
        asyncio.create_task(self.process(activity_id=activity_id, team_id=team_id))

    async def trigger_evaluation(self, activity_id: int, team_id: int) -> None:
        asyncio.create_task(self.evaluate(activity_id=activity_id, team_id=team_id))

    async def run_post_commit_workflow(
        self,
        *,
        activity_id: int,
        team_id: int,
        trigger_type: str,
        actor_id: str | None = None,
    ) -> Dict[str, Any]:
        logger.info(
            "开始客户活动后提交 workflow: activity_id=%s, team_id=%s, trigger_type=%s",
            activity_id,
            team_id,
            trigger_type,
        )
        try:
            state = await customer_activity_post_commit_workflow.run(
                activity_id=activity_id,
                team_id=team_id,
                trigger_type=trigger_type,
                actor_id=actor_id,
            )
            logger.info(
                "客户活动后提交 workflow 完成: activity_id=%s, skip_reason=%s, error=%s",
                activity_id,
                state.get("skip_reason"),
                state.get("error_message"),
            )
            return {
                "success": not bool(state.get("error_message")),
                "activity_id": activity_id,
                "skip_reason": state.get("skip_reason"),
                "error": state.get("error_message"),
                "projection_result": state.get("projection_result"),
                "match_result": state.get("match_result"),
                "transition_plan": state.get("transition_plan"),
                "policy_results": state.get("policy_results") or [],
                "execution_results": state.get("execution_results") or [],
                "confirmation_cases": state.get("confirmation_cases") or [],
                "post_commit": state.get("post_commit") or _empty_post_commit_outcome(),
            }
        except Exception as exc:
            logger.exception("客户活动后提交 workflow 调度失败: activity_id=%s", activity_id)
            return {
                "success": False,
                "activity_id": activity_id,
                "error": str(exc),
                "post_commit": _empty_post_commit_outcome(),
            }

    async def trigger_post_commit_workflow(
        self,
        *,
        activity_id: int,
        team_id: int,
        trigger_type: str,
        actor_id: str | None = None,
    ) -> None:
        asyncio.create_task(
            self.run_post_commit_workflow(
                activity_id=activity_id,
                team_id=team_id,
                trigger_type=trigger_type,
                actor_id=actor_id,
            )
        )

    async def recover_unfinished(self, limit: int = 100) -> int:
        db = SessionLocal()
        try:
            activities = customer_activity_crud.get_unfinished_ai_activities(db, limit=limit)
            jobs = [
                (activity.id, activity.team_id, activity.processing_status, activity.effectiveness_status)
                for activity in activities
            ]
        finally:
            db.close()

        for activity_id, team_id, processing_status, effectiveness_status in jobs:
            if processing_status in {"PENDING", "PROCESSING"}:
                asyncio.create_task(self.process(activity_id=activity_id, team_id=team_id))
            elif effectiveness_status == "GENERATING":
                asyncio.create_task(self.evaluate(activity_id=activity_id, team_id=team_id))
        return len(jobs)

    def _mark_processing_failed(self, activity_id: int, error_message: str) -> None:
        db = SessionLocal()
        try:
            customer_activity_crud.update_processing_status(db, activity_id, "FAILED", error_message)
        finally:
            db.close()

    def _mark_evaluation_failed(self, activity_id: int, error_message: str) -> None:
        db = SessionLocal()
        try:
            customer_activity_crud.update_effectiveness_status(db, activity_id, "FAILED", error_message)
        finally:
            db.close()


customer_activity_processing_service = CustomerActivityProcessingService()
