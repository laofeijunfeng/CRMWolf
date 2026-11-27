"""Idempotent historical customer-activity Markdown upgrade service (CRM-180)."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from app.core.database import SessionLocal
from app.crud.ai_config import ai_config_crud
from app.crud.customer_activity import (
    ACTIVITY_MARKDOWN_FORMAT_VERSION,
    CustomerActivityCRUD,
    customer_activity_crud,
    has_markdown_format_version,
)
from app.models.customer_activity import CustomerActivity
from app.services.ai_task_limiter import ai_generation_semaphore
from app.services.customer_activity_ai.structuring_agent import (
    ActivityStructuringAgent,
    activity_structuring_agent,
)
from app.services.customer_activity_contracts import CustomerActivityProcessingStatus
from app.services.customer_activity_kinds import get_activity_kind_meta
from app.utils.time import business_now

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)
_MAX_RECORDED_ERRORS = 50


@dataclass
class CustomerActivityMarkdownBackfillResult:
    dry_run: bool
    scanned: int = 0
    candidates: int = 0
    upgraded: int = 0
    skipped_already_upgraded: int = 0
    skipped_empty: int = 0
    skipped_no_ai_config: int = 0
    failed: int = 0
    activity_ids: list[int] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "target_markdown_format_version": ACTIVITY_MARKDOWN_FORMAT_VERSION,
            "scanned": self.scanned,
            "candidates": self.candidates,
            "upgraded": self.upgraded,
            "skipped_already_upgraded": self.skipped_already_upgraded,
            "skipped_empty": self.skipped_empty,
            "skipped_no_ai_config": self.skipped_no_ai_config,
            "failed": self.failed,
            "activity_ids": self.activity_ids,
            "errors": self.errors,
        }


class CustomerActivityMarkdownBackfillService:
    """Safely upgrade historical completed customer activities to structured Markdown.

    Safety invariants:
    - Never touches `crm_lead_follow_ups` (Lead follow-up records remain plain text).
    - Never overwrites immutable historical facts (`occurred_at`, `creator_id`, `owner_id`,
      `activity_kind`, `source_content`, `next_action`, `next_follow_time`, `original_lead_id`).
    - Never re-triggers post-commit side effects (follow-up task creation, customer
      intelligence refresh, notifications).
    - Preserves `source_content` and existing `summary` on LLM/DB failure.
    - Idempotent: stamps `content_json.markdown_format_version = 1` and skips already upgraded rows.
    """

    def __init__(
        self,
        *,
        structuring_agent: ActivityStructuringAgent | None = None,
        activity_crud: CustomerActivityCRUD | None = None,
    ) -> None:
        self.structuring_agent = structuring_agent or activity_structuring_agent
        self.activity_crud = activity_crud or customer_activity_crud

    def list_candidates(
        self,
        db: Session,
        *,
        team_id: int | None = None,
        days: int | None = None,
        limit: int | None = None,
    ) -> tuple[list[CustomerActivity], dict[str, int]]:
        query = db.query(CustomerActivity).filter(
            CustomerActivity.processing_status == CustomerActivityProcessingStatus.COMPLETED.value,
        )
        if team_id is not None:
            query = query.filter(CustomerActivity.team_id == team_id)
        if days is not None:
            cutoff = business_now() - timedelta(days=max(1, int(days)))
            query = query.filter(CustomerActivity.occurred_at >= cutoff)

        rows = query.order_by(CustomerActivity.id.asc()).all()
        candidates: list[CustomerActivity] = []
        counts = {
            "scanned": 0,
            "skipped_already_upgraded": 0,
            "skipped_empty": 0,
        }
        for row in rows:
            counts["scanned"] += 1
            if not (row.source_content or "").strip():
                counts["skipped_empty"] += 1
                continue
            if has_markdown_format_version(row.content_json):
                counts["skipped_already_upgraded"] += 1
                continue
            candidates.append(row)
            if limit is not None and len(candidates) >= max(1, int(limit)):
                break
        return candidates, counts

    @staticmethod
    def _build_structuring_context(activity: CustomerActivity) -> dict[str, Any]:
        meta = get_activity_kind_meta(activity.activity_kind)
        return {
            "current_activity": {
                "activity_kind": activity.activity_kind,
                "activity_category": meta["category"],
                "activity_label": meta["label"],
                "occurred_at": activity.occurred_at.isoformat() if activity.occurred_at else "",
                "next_action": activity.next_action or "",
                "source_content": activity.source_content or "",
            }
        }

    async def upgrade_activity_by_id(
        self,
        *,
        session_factory: Callable[[], Session],
        activity_id: int,
        team_id: int,
    ) -> tuple[str, str | None]:
        db = session_factory()
        try:
            activity = self.activity_crud.get_by_id(db, activity_id, team_id)
            if activity is None:
                return ("skipped_already_upgraded", None)
            if activity.processing_status != CustomerActivityProcessingStatus.COMPLETED.value:
                return ("skipped_already_upgraded", None)
            if not (activity.source_content or "").strip():
                return ("skipped_empty", None)
            if has_markdown_format_version(activity.content_json):
                return ("skipped_already_upgraded", None)

            config = ai_config_crud.get_config(db, team_id)
            api_key = ai_config_crud.get_decrypted_api_key(db, team_id) if config else None
            if not config or not api_key:
                return ("skipped_no_ai_config", None)

            context = self._build_structuring_context(activity)
            async with ai_generation_semaphore:
                structured = await self.structuring_agent.structure(
                    db,
                    team_id=team_id,
                    context=context,
                )

            self.activity_crud.apply_historical_markdown_upgrade(
                db,
                activity,
                title=structured.get("title"),
                content_json=structured.get("content_json"),
                summary=structured.get("summary"),
                commit=True,
            )
            return ("upgraded", None)
        except Exception as exc:
            db.rollback()
            error = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "历史客户活动 Markdown 升级失败: activity_id=%s team_id=%s error=%s",
                activity_id,
                team_id,
                error,
            )
            return ("failed", error)
        finally:
            db.close()

    async def backfill_activities(
        self,
        *,
        session_factory: Callable[[], Session] = SessionLocal,
        team_id: int | None = None,
        days: int | None = None,
        limit: int | None = 500,
        concurrency: int = 2,
        dry_run: bool = True,
    ) -> CustomerActivityMarkdownBackfillResult:
        scan_db = session_factory()
        try:
            candidates, counts = self.list_candidates(
                scan_db,
                team_id=team_id,
                days=days,
                limit=limit,
            )
            targets = [(int(item.id), int(item.team_id)) for item in candidates]
        finally:
            scan_db.close()

        result = CustomerActivityMarkdownBackfillResult(
            dry_run=dry_run,
            scanned=counts["scanned"],
            candidates=len(targets),
            skipped_already_upgraded=counts["skipped_already_upgraded"],
            skipped_empty=counts["skipped_empty"],
        )
        if dry_run or not targets:
            result.activity_ids = [activity_id for activity_id, _ in targets]
            return result

        worker_semaphore = asyncio.Semaphore(max(1, int(concurrency)))

        async def _run_one(activity_id: int, item_team_id: int) -> tuple[int, str, str | None]:
            async with worker_semaphore:
                status, error = await self.upgrade_activity_by_id(
                    session_factory=session_factory,
                    activity_id=activity_id,
                    team_id=item_team_id,
                )
                return (activity_id, status, error)

        outcomes = await asyncio.gather(*(_run_one(aid, tid) for aid, tid in targets))
        for activity_id, status, error in outcomes:
            if status == "upgraded":
                result.upgraded += 1
                result.activity_ids.append(activity_id)
            elif status == "skipped_already_upgraded":
                result.skipped_already_upgraded += 1
            elif status == "skipped_empty":
                result.skipped_empty += 1
            elif status == "skipped_no_ai_config":
                result.skipped_no_ai_config += 1
            else:
                result.failed += 1
                if len(result.errors) < _MAX_RECORDED_ERRORS:
                    result.errors.append({"activity_id": activity_id, "error": error or "unknown error"})

        return result


customer_activity_markdown_backfill_service = CustomerActivityMarkdownBackfillService()
