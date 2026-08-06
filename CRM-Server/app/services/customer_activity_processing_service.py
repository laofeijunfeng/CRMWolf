"""Async entrypoint for customer activity AI workflows."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from app.crud.customer_activity import customer_activity_crud
from app.services.ai_task_limiter import ai_generation_semaphore
from app.services.customer_activity_ai.evaluation_agent import ActivityEvaluationError
from app.services.customer_activity_ai.structuring_agent import ActivityStructuringError
from app.services.customer_activity_ai.workflow import customer_activity_ai_workflow
from app.core.database import SessionLocal
from app.services.follow_up_task_projection_service import follow_up_task_projection_service


logger = logging.getLogger(__name__)


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

    async def project_follow_up_task(
        self,
        *,
        activity_id: int,
        team_id: int,
        trigger_type: str,
        actor_id: str | None = None,
    ) -> Dict[str, Any]:
        logger.info(
            "开始客户活动任务投影: activity_id=%s, team_id=%s, trigger_type=%s",
            activity_id,
            team_id,
            trigger_type,
        )
        db = SessionLocal()
        try:
            try:
                result = follow_up_task_projection_service.run_activity_projection(
                    db,
                    activity_id=activity_id,
                    team_id=team_id,
                    trigger_type=trigger_type,
                    actor_id=actor_id,
                )
                logger.info(
                    "客户活动任务投影完成: activity_id=%s, status=%s, skip_reason=%s",
                    activity_id,
                    result.projection_run_status,
                    result.skip_reason,
                )
                return {
                    "success": result.projection_run_status != "FAILED",
                    "activity_id": activity_id,
                    "projection_run_id": result.projection_run_id,
                    "status": result.projection_run_status,
                    "skip_reason": result.skip_reason,
                    "error": result.error_message,
                }
            except Exception as exc:
                logger.exception("客户活动任务投影调度失败: activity_id=%s", activity_id)
                return {"success": False, "activity_id": activity_id, "error": str(exc)}
        finally:
            db.close()

    async def trigger_follow_up_task_projection(
        self,
        *,
        activity_id: int,
        team_id: int,
        trigger_type: str,
        actor_id: str | None = None,
    ) -> None:
        asyncio.create_task(
            self.project_follow_up_task(
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
