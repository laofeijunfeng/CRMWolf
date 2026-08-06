import json
import logging
from datetime import datetime

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.customer_activity import CustomerActivity
from app.models.lead import LeadFollowUp
from app.schemas.customer_activity import CustomerActivityCreate, CustomerActivityUpdate
from app.services.customer_activity_kinds import FOLLOW_UP_METHOD_TO_KIND, CustomerActivityKind, get_activity_kind_meta
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


def _upsert_customer_activity_evidence(db: Session, activity: CustomerActivity) -> None:
    try:
        from app.services.customer_vector_document_service import customer_vector_document_service

        customer_vector_document_service.upsert_customer_activity(db, activity)
    except Exception:
        logger.exception("客户活动证据元数据写入失败: activity_id=%s", activity.id)


def _mark_customer_activity_evidence_deleted(db: Session, activity: CustomerActivity) -> None:
    try:
        from app.services.customer_vector_document_service import customer_vector_document_service

        customer_vector_document_service.mark_customer_activity_deleted(db, activity)
    except Exception:
        logger.exception("客户活动证据元数据删除标记失败: activity_id=%s", activity.id)


class CustomerActivityCRUD:
    def get_by_id(self, db: Session, activity_id: int, team_id: int | None = None) -> CustomerActivity | None:
        query = db.query(CustomerActivity).filter(CustomerActivity.id == activity_id)
        if team_id is not None:
            query = query.filter(CustomerActivity.team_id == team_id)
        return query.first()

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
    ) -> CustomerActivity:
        from app.services.deal_journey_service import deal_journey_service
        from app.services.operation_log_service import operation_log_service

        data = obj_in.model_dump()
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
        data["occurred_at"] = data.get("occurred_at") or business_now()
        if data.get("next_follow_time") is not None and not data.get("next_follow_time_source"):
            data["next_follow_time_source"] = "USER"
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
        db.commit()
        db.refresh(db_obj)

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
        )
        db.commit()

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
        )
        _upsert_customer_activity_evidence(db, db_obj)
        return db_obj

    def migrate_from_lead(
        self,
        db: Session,
        lead_id: int,
        new_customer_id: int,
        team_id: int,
    ) -> list[CustomerActivity]:
        lead_follow_ups = db.query(LeadFollowUp).filter(LeadFollowUp.lead_id == lead_id).all()
        migrated = []
        for lead_follow_up in lead_follow_ups:
            method = lead_follow_up.method.value if hasattr(lead_follow_up.method, "value") else lead_follow_up.method
            kind = FOLLOW_UP_METHOD_TO_KIND.get(method, CustomerActivityKind.OTHER_FOLLOW_UP)
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
                occurred_at=lead_follow_up.created_time or business_now(),
                creator_id=lead_follow_up.creator_id,
                owner_id=lead_follow_up.creator_id,
                created_time=lead_follow_up.created_time,
            )
            db.add(activity)
            migrated.append(activity)
        db.commit()
        for activity in migrated:
            db.refresh(activity)
            _upsert_customer_activity_evidence(db, activity)
        return migrated

    def update(self, db: Session, db_obj: CustomerActivity, obj_in: CustomerActivityUpdate) -> CustomerActivity:
        update_data = obj_in.model_dump(exclude_unset=True)
        if "content_json" in update_data:
            update_data["content_json"] = _json_dumps(update_data["content_json"])
        if "source_content" in update_data:
            update_data["processing_status"] = "PENDING"
            update_data["processing_error"] = None
            update_data["processed_at"] = None
        if "next_follow_time" in update_data and "next_follow_time_source" not in update_data:
            update_data["next_follow_time_source"] = "USER"
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        db.commit()
        db.refresh(db_obj)
        _upsert_customer_activity_evidence(db, db_obj)
        return db_obj

    def update_next_time(
        self,
        db: Session,
        db_obj: CustomerActivity,
        next_follow_time: datetime | None,
    ) -> CustomerActivity:
        db_obj.next_follow_time = next_follow_time
        db_obj.next_follow_time_source = "USER"
        db.commit()
        db.refresh(db_obj)
        _upsert_customer_activity_evidence(db, db_obj)
        return db_obj

    def update_processing_status(
        self,
        db: Session,
        activity_id: int,
        status: str,
        error_message: str | None = None,
    ) -> CustomerActivity | None:
        activity = self.get_by_id(db, activity_id)
        if not activity:
            return None
        activity.processing_status = status
        activity.processing_error = error_message
        if status == "COMPLETED":
            activity.processed_at = business_now()
        db.commit()
        db.refresh(activity)
        _upsert_customer_activity_evidence(db, activity)
        return activity

    def update_processed_content(
        self,
        db: Session,
        activity_id: int,
        *,
        title: str | None,
        content_json: JSONObject,
        summary: str | None,
        next_action: str | None = None,
        next_follow_time: datetime | None = None,
        next_follow_time_source: str | None = None,
    ) -> CustomerActivity | None:
        activity = self.get_by_id(db, activity_id)
        if not activity:
            return None
        activity.title = title or self.build_title(activity.activity_kind, content_json)
        activity.content_json = _json_dumps(content_json)
        activity.summary = summary or self.build_summary(activity.activity_kind, content_json, activity.source_content)
        if next_action is not None:
            activity.next_action = next_action
        if next_follow_time is not None:
            activity.next_follow_time = next_follow_time
            activity.next_follow_time_source = next_follow_time_source or "AI_EXTRACTED"
        activity.processing_status = "COMPLETED"
        activity.processing_error = None
        activity.processed_at = business_now()
        db.commit()
        db.refresh(activity)
        _upsert_customer_activity_evidence(db, activity)
        return activity

    def update_effectiveness_status(
        self,
        db: Session,
        activity_id: int,
        status: str,
        error_message: str | None = None,
    ) -> CustomerActivity | None:
        activity = self.get_by_id(db, activity_id)
        if not activity:
            return None
        activity.effectiveness_status = status
        activity.effectiveness_error_message = error_message
        if status in {"PENDING", "GENERATING"}:
            activity.effectiveness_score = None
            activity.effectiveness_is_valid = None
            activity.effectiveness_reason = None
            activity.effectiveness_detail_json = None
            activity.effectiveness_evaluated_time = None
        elif status == "FAILED":
            activity.effectiveness_evaluated_time = business_now()
        db.commit()
        db.refresh(activity)
        return activity

    def update_effectiveness_result(
        self,
        db: Session,
        activity_id: int,
        score: int,
        is_valid: bool,
        reason: str,
        detail_json: str | None = None,
    ) -> CustomerActivity | None:
        activity = self.get_by_id(db, activity_id)
        if not activity:
            return None
        activity.effectiveness_score = score
        activity.effectiveness_is_valid = is_valid
        activity.effectiveness_reason = reason
        activity.effectiveness_detail_json = detail_json
        activity.effectiveness_status = "COMPLETED"
        activity.effectiveness_evaluated_time = business_now()
        activity.effectiveness_error_message = None
        db.commit()
        db.refresh(activity)
        return activity

    def delete(self, db: Session, db_obj: CustomerActivity) -> CustomerActivity:
        _mark_customer_activity_evidence_deleted(db, db_obj)
        db.delete(db_obj)
        db.commit()
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
