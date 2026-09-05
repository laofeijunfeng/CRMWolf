import json
import logging
from datetime import datetime

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.customer_activity import CustomerActivity
from app.models.customer_activity_deletion import CustomerActivityDeletionTombstone
from app.models.lead import LeadFollowUp
from app.schemas.customer_activity import CustomerActivityCreate
from app.services.customer_activity_contracts import CustomerActivitySubmissionSource
from app.services.customer_activity_kinds import get_activity_kind_meta
from app.services.legacy_customer_activity_adapter import activity_kind_from_legacy_lead_method
from app.utils.time import business_now

logger = logging.getLogger(__name__)

JSONPrimitive = str | int | float | bool | None
JSONValue = JSONPrimitive | list["JSONValue"] | dict[str, "JSONValue"]
JSONObject = dict[str, JSONValue]


def _json_dumps(value: JSONValue) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _default_content_json(activity_kind: str, source_content: str, next_action: str | None = None) -> JSONObject:
    meta = get_activity_kind_meta(activity_kind)
    if meta["category"] == "MEETING":
        return {
            "meeting_subject": "",
            "meeting_background": "",
            "communication_context": "",
            "participants": {"internal": [], "customer": []},
            "key_minutes": [source_content],
            "qa_items": [],
            "requirements": [],
            "concerns_or_objections": [],
            "risks": [],
            "decisions_or_commitments": [],
            "action_items": [],
            "next_step_summary": next_action or "",
        }
    return {
        "content": source_content,
        "customer_feedback": "",
        "current_progress": "",
        "risks": [],
        "next_action": next_action or "",
        "next_follow_time_text": "",
    }


def _upsert_customer_activity_evidence(
    db: Session,
    activity: CustomerActivity,
    *,
    commit: bool = True,
) -> None:
    try:
        from app.services.customer_vector_document_service import customer_vector_document_service

        customer_vector_document_service.upsert_customer_activity(db, activity, commit=commit)
    except Exception:
        logger.exception("客户活动证据元数据写入失败: activity_id=%s", activity.id)


def _mark_customer_activity_evidence_deleted(db: Session, activity: CustomerActivity) -> None:
    try:
        from app.services.customer_vector_document_service import customer_vector_document_service

        customer_vector_document_service.mark_customer_activity_deleted(db, activity)
    except Exception:
        logger.exception("客户活动证据元数据删除标记失败: activity_id=%s", activity.id)


POST_COMMIT_RELEVANT_FIELDS = frozenset(
    {
        "activity_kind",
        "source_content",
        "content_json",
        "summary",
        "next_follow_time",
        "next_follow_time_source",
        "next_action",
        "next_action_source",
        "occurred_at",
        "owner_id",
        "customer_id",
    }
)


def _post_commit_value(value: object) -> object:
    """Normalize mutable/serialized activity values before revision comparison."""

    if isinstance(value, dict):
        return _json_dumps(value)
    return value


def _post_commit_fields_changed(db_obj: CustomerActivity, values: dict[str, object]) -> bool:
    return any(
        field in POST_COMMIT_RELEVANT_FIELDS
        and _post_commit_value(getattr(db_obj, field, None)) != _post_commit_value(value)
        for field, value in values.items()
    )


class CustomerActivityCRUD:
    def get_by_id(self, db: Session, activity_id: int, team_id: int | None = None) -> CustomerActivity | None:
        query = db.query(CustomerActivity).filter(CustomerActivity.id == activity_id)
        if team_id is not None:
            query = query.filter(CustomerActivity.team_id == team_id)
        return query.first()

    def get_by_submission_id(
        self,
        db: Session,
        *,
        team_id: int,
        submission_id: str,
    ) -> CustomerActivity | None:
        return (
            db.query(CustomerActivity)
            .filter(
                CustomerActivity.team_id == team_id,
                CustomerActivity.submission_id == submission_id,
            )
            .one_or_none()
        )

    def get_by_customer_id(
        self,
        db: Session,
        customer_id: int,
        team_id: int | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[CustomerActivity], int]:
        query = db.query(CustomerActivity).filter(CustomerActivity.customer_id == customer_id)
        if team_id is not None:
            query = query.filter(CustomerActivity.team_id == team_id)
        total = query.count()
        activities = (
            query.order_by(CustomerActivity.occurred_at.desc(), CustomerActivity.id.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        return activities, total

    def get_by_original_lead_id(
        self,
        db: Session,
        lead_id: int,
        team_id: int | None = None,
    ) -> list[CustomerActivity]:
        query = db.query(CustomerActivity).filter(CustomerActivity.original_lead_id == lead_id)
        if team_id is not None:
            query = query.filter(CustomerActivity.team_id == team_id)
        return query.order_by(CustomerActivity.occurred_at.asc(), CustomerActivity.id.asc()).all()

    def get_unfinished_ai_activities(self, db: Session, limit: int = 100) -> list[CustomerActivity]:
        return (
            db.query(CustomerActivity)
            .filter(
                or_(
                    CustomerActivity.processing_status.in_(["PENDING", "PROCESSING"]),
                    CustomerActivity.effectiveness_status == "GENERATING",
                )
            )
            .order_by(CustomerActivity.updated_time.asc(), CustomerActivity.id.asc())
            .limit(limit)
            .all()
        )

    def create(
        self,
        db: Session,
        obj_in: CustomerActivityCreate,
        customer_id: int,
        creator_id: str,
        team_id: int,
        operator_name: str | None = None,
        original_lead_id: int | None = None,
        owner_id: str | None = None,
        submission_source: str | None = None,
        submission_id: str | None = None,
        submission_fingerprint: str | None = None,
        commit: bool = True,
    ) -> CustomerActivity:
        from app.services.deal_journey_service import deal_journey_service
        from app.services.operation_log_service import operation_log_service

        data = obj_in.model_dump()
        effectiveness_detail = data.get("effectiveness_detail_json")
        if isinstance(effectiveness_detail, (dict, list)):
            data["effectiveness_detail_json"] = _json_dumps(effectiveness_detail)
        content_json = data.pop("content_json", None) or _default_content_json(
            data["activity_kind"],
            data["source_content"],
            data.get("next_action"),
        )
        data["content_json"] = _json_dumps(content_json)
        data["customer_id"] = customer_id
        data["creator_id"] = creator_id
        data["owner_id"] = owner_id or creator_id
        data["team_id"] = team_id
        data["activity_revision"] = 1
        data["submission_source"] = (
            submission_source
            or data.get("submission_source")
            or CustomerActivitySubmissionSource.FORM.value
        )
        data["submission_id"] = submission_id or data.get("submission_id")
        data["submission_fingerprint"] = submission_fingerprint
        data["occurred_at"] = data.get("occurred_at") or business_now()
        if data.get("next_follow_time") is not None and not data.get("next_follow_time_source"):
            data["next_follow_time_source"] = "USER"
        if data.get("next_action") and not data.get("next_action_source"):
            data["next_action_source"] = "USER"
        if original_lead_id:
            data["original_lead_id"] = original_lead_id

        if data.get("summary") is None:
            data["summary"] = self.build_summary(data["activity_kind"], content_json, data["source_content"])
        if data.get("title") is None:
            data["title"] = self.build_title(data["activity_kind"], content_json)

        journey = deal_journey_service.infer_for_customer(db, customer_id, team_id)
        if journey:
            data["deal_journey_id"] = journey.id

        db_obj = CustomerActivity(**data)
        db.add(db_obj)
        db.flush()

        from app.models.deal_journey import DealJourneyEventType, DealJourneySourceType

        label = get_activity_kind_meta(db_obj.activity_kind)["label"]
        deal_journey_service.record_event(
            db,
            deal_journey_id=db_obj.deal_journey_id,
            team_id=team_id,
            customer_id=customer_id,
            event_type=DealJourneyEventType.ACTIVITY_ADDED,
            source_type=DealJourneySourceType.CUSTOMER_ACTIVITY,
            source_id=db_obj.id,
            event_time=db_obj.occurred_at,
            actor_id=creator_id,
            summary=f"新增客户活动: {label}",
            # CustomerActivityWriteService enqueues the canonical, revision-scoped
            # intelligence event in the same transaction. The journey event remains
            # evidence/audit and must not create a duplicate intelligence run.
            enqueue_customer_intelligence=False,
        )

        operation_log_service.log_customer_activity(
            db=db,
            customer_id=customer_id,
            activity_content=db_obj.summary or db_obj.source_content,
            activity_kind=label,
            operator_id=creator_id,
            operator_name=operator_name,
            next_follow_time=db_obj.next_follow_time.strftime("%Y-%m-%d") if db_obj.next_follow_time else None,
            next_action=db_obj.next_action,
            team_id=team_id,
            activity_id=db_obj.id,
            commit=False,
        )
        _upsert_customer_activity_evidence(db, db_obj, commit=False)
        if commit:
            db.commit()
            db.refresh(db_obj)
        else:
            db.flush()
        return db_obj

    def migrate_from_lead(
        self,
        db: Session,
        lead_id: int,
        new_customer_id: int,
        team_id: int,
        *,
        commit: bool = True,
    ) -> list[CustomerActivity]:
        lead_follow_ups = db.query(LeadFollowUp).filter(LeadFollowUp.lead_id == lead_id).all()
        migrated = []
        for lead_follow_up in lead_follow_ups:
            kind = activity_kind_from_legacy_lead_method(lead_follow_up.method)
            content_json = _default_content_json(kind, lead_follow_up.content, lead_follow_up.next_action)
            activity = CustomerActivity(
                customer_id=new_customer_id,
                team_id=team_id,
                deal_journey_id=None,
                original_lead_id=lead_id,
                activity_kind=kind,
                title=self.build_title(kind, content_json),
                source_content=lead_follow_up.content,
                content_json=_json_dumps(content_json),
                summary=self.build_summary(kind, content_json, lead_follow_up.content),
                processing_status="COMPLETED",
                processed_at=lead_follow_up.created_time,
                next_follow_time=lead_follow_up.next_follow_time,
                next_follow_time_source="MIGRATED" if lead_follow_up.next_follow_time else None,
                next_action=lead_follow_up.next_action,
                next_action_source="MIGRATED" if lead_follow_up.next_action else None,
                occurred_at=lead_follow_up.created_time or business_now(),
                creator_id=lead_follow_up.creator_id,
                owner_id=lead_follow_up.creator_id,
                created_time=lead_follow_up.created_time,
            )
            db.add(activity)
            migrated.append(activity)
        if commit:
            db.commit()
            for activity in migrated:
                db.refresh(activity)
                _upsert_customer_activity_evidence(db, activity)
        else:
            db.flush()
            for activity in migrated:
                _upsert_customer_activity_evidence(db, activity, commit=False)
        return migrated


    def apply_finalization(
        self,
        db: Session,
        activity: CustomerActivity,
        *,
        title: str | None,
        content_json: JSONObject,
        summary: str | None,
        next_action: str | None,
        next_action_source: str | None,
        next_follow_time: datetime | None,
        next_follow_time_source: str | None,
        effectiveness_score: int,
        effectiveness_is_valid: bool,
        effectiveness_reason: str,
        effectiveness_detail_json: str | None,
        increment_revision: bool,
        commit: bool = True,
    ) -> CustomerActivity:
        """Persist one canonical structured-and-scored activity result."""

        resolved_summary = summary or self.build_summary(
            activity.activity_kind,
            content_json,
            activity.source_content,
        )
        structured_values: dict[str, object] = {
            "content_json": content_json,
            "summary": resolved_summary,
        }
        if next_action is not None:
            structured_values["next_action"] = next_action
            structured_values["next_action_source"] = next_action_source or "AI_EXTRACTED"
        if next_follow_time is not None:
            structured_values["next_follow_time"] = next_follow_time
            structured_values["next_follow_time_source"] = next_follow_time_source or "AI_EXTRACTED"

        revision_changed = _post_commit_fields_changed(activity, structured_values)
        activity.title = title or self.build_title(activity.activity_kind, content_json)
        activity.content_json = _json_dumps(content_json)
        activity.summary = resolved_summary
        if next_action is not None:
            activity.next_action = next_action
            activity.next_action_source = str(structured_values["next_action_source"])
        if next_follow_time is not None:
            activity.next_follow_time = next_follow_time
            activity.next_follow_time_source = str(structured_values["next_follow_time_source"])
        if increment_revision and revision_changed:
            activity.activity_revision = int(activity.activity_revision or 1) + 1

        now = business_now()
        activity.processing_status = "COMPLETED"
        activity.processing_error = None
        activity.processed_at = now
        activity.effectiveness_score = effectiveness_score
        activity.effectiveness_is_valid = effectiveness_is_valid
        activity.effectiveness_reason = effectiveness_reason
        activity.effectiveness_detail_json = effectiveness_detail_json
        activity.effectiveness_status = "COMPLETED"
        activity.effectiveness_evaluated_time = now
        activity.effectiveness_error_message = None
        _upsert_customer_activity_evidence(db, activity, commit=False)
        if commit:
            db.commit()
            db.refresh(activity)
        else:
            db.flush()
        return activity


    def delete(
        self,
        db: Session,
        db_obj: CustomerActivity,
        *,
        commit: bool = True,
        deleted_by: str | None = None,
    ) -> CustomerActivity:
        _mark_customer_activity_evidence_deleted(db, db_obj)
        # The operational activity row is hard-deleted, so keep a durable
        # source-side tombstone in the same transaction.  Its monotonically
        # increasing ID is included in the customer context watermark; if the
        # async profile enqueue is lost after commit, reconciliation still
        # observes this deletion and rebuilds the profile without the row.
        if db_obj.customer_id is not None:
            db.add(
                CustomerActivityDeletionTombstone(
                    team_id=db_obj.team_id,
                    customer_id=db_obj.customer_id,
                    activity_id=db_obj.id,
                    deal_journey_id=db_obj.deal_journey_id,
                    activity_occurred_at=db_obj.occurred_at,
                    activity_revision=db_obj.activity_revision,
                    deleted_by=deleted_by,
                )
            )
            db.flush()
        db.delete(db_obj)
        if commit:
            db.commit()
        else:
            db.flush()
        return db_obj

    def build_title(self, activity_kind: str, content_json: JSONObject) -> str:
        meta = get_activity_kind_meta(activity_kind)
        if meta["category"] == "MEETING":
            subject = str(content_json.get("meeting_subject") or "").strip()
            return subject or meta["label"]
        return meta["label"]

    def build_summary(self, activity_kind: str, content_json: JSONObject, source_content: str) -> str:
        meta = get_activity_kind_meta(activity_kind)
        if meta["category"] == "MEETING":
            minutes = content_json.get("key_minutes")
            if isinstance(minutes, list) and minutes:
                return str(minutes[0])[:300]
        content = content_json.get("content") if isinstance(content_json, dict) else None
        return str(content or source_content or "")[:300]


customer_activity_crud = CustomerActivityCRUD()
