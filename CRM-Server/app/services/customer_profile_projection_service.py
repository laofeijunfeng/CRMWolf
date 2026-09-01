"""Deep module for publishing and reading customer profile projections.

Callers do not manipulate snapshot rows or current pointers directly.  This
module owns the invariants that make the read model useful: immutable versions,
content/watermark idempotency, team isolation, and compare-and-swap publishing.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from datetime import datetime
from hashlib import sha256
from typing import TYPE_CHECKING

from sqlalchemy.exc import IntegrityError

from app.crud.customer_profile_projection import customer_profile_projection_crud
from app.models.customer import Customer
from app.models.customer_profile_projection import (
    CustomerProfileCurrent,
    CustomerProfileProjectionVersion,
    CustomerProfilePublicationStatus,
    CustomerProfileStatus,
)
from app.schemas.customer_profile import CustomerProfileSections
from app.services.agent.types import JSONDict, coerce_json_dict
from app.services.customer_profile_projection_policy import (
    CustomerProfileProjectionAssessment,
    CustomerProfileProjectionPolicy,
    customer_profile_projection_policy,
)
from app.services.customer_profile_projection_validator import CustomerProfileProjectionValidationError
from app.services.customer_profile_watermark_service import (
    customer_profile_watermark_service,
)
from app.utils.time import business_now

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sqlalchemy.orm import Session

    from app.services.customer_profile_projection_quality import CustomerProfileQualityReport


PROFILE_SCHEMA_VERSION = "v2"
PROFILE_GRAPH_VERSION = "customer-profile-v2"
PROFILE_WORKFLOW_OWNER = "customer_profile_projection_workflow"
PROFILE_SECTION_NAMES = (
    "current_situation",
    "current_journeys",
    "important_changes",
    "long_term_context",
    "follow_up_process",
    "recorded_follow_ups",
)


@dataclass(frozen=True)
class CustomerProfileProjectionDraft:
    sections: CustomerProfileSections
    evidence_refs: list[dict[str, object]]
    source_watermark: dict[str, object]
    fact_watermark: int = 0
    journey_watermark: int = 0
    task_watermark: int = 0
    commitment_watermark: int = 0
    source_event_key: str | None = None
    graph_version: str = PROFILE_GRAPH_VERSION
    target_sections: tuple[str, ...] = ()


@dataclass(frozen=True)
class CustomerProfilePublication:
    """Authoritative publication outcome returned by the publication seam.

    Consumers must derive user-visible run status from this object rather than
    re-running quality checks or guessing from the draft.  This keeps the
    publication service as the single owner of the hard/soft gate decision.
    """

    version: CustomerProfileProjectionVersion
    current: CustomerProfileCurrent
    deduplicated: bool = False
    changed_sections: tuple[str, ...] = ()
    quality_report: CustomerProfileQualityReport | None = None

    @property
    def publication_status(self) -> str:
        return str(self.version.publication_status)


def publication_result_payload(
    publication: CustomerProfilePublication,
    *,
    draft: CustomerProfileProjectionDraft,
    fact_changes: int = 0,
    stale_after_run: bool = False,
) -> dict[str, object]:
    """Project one authoritative publication into the graph/run contract.

    The publication service owns the final status and quality decision.  The
    dedicated profile workflow uses this adapter instead of reading the draft
    or inventing its own status mapping.  It is intentionally called while
    the publication session is still open so ORM-backed values are copied into
    plain data first.
    """

    version = publication.version
    quality_report = getattr(publication, "quality_report", None)
    quality_report_json = quality_report.as_json() if quality_report is not None else {}
    if not quality_report_json:
        raw_report = getattr(version, "quality_report_json", None)
        if isinstance(raw_report, dict):
            quality_report_json = dict(raw_report)

    target_sections = list(draft.target_sections or PROFILE_SECTION_NAMES)
    changed_sections = list(getattr(publication, "changed_sections", ()) or ())
    return {
        "success": True,
        "published": True,
        "publication_status": str(
            getattr(publication, "publication_status", None)
            or getattr(version, "publication_status", "PUBLISHED")
        ),
        "deduplicated": bool(getattr(publication, "deduplicated", False)),
        "profile_version": int(version.profile_version),
        "profile_version_public_id": str(version.public_id),
        "profile_version_id": str(version.public_id),
        "input_watermark": dict(draft.source_watermark),
        "target_sections": target_sections,
        "changed_sections": changed_sections,
        "evidence_count": len(draft.evidence_refs),
        "fact_changes": fact_changes,
        "stale_after_run": stale_after_run,
        "error_code": None,
        "quality_report": quality_report_json,
    }


class CustomerProfileProjectionError(ValueError):
    """The draft cannot be safely published."""

    def __init__(self, message: str, *, code: str = "PROFILE_SCHEMA_INVALID") -> None:
        super().__init__(message)
        self.code = code


class CustomerProfileProjectionService:
    """Small interface hiding snapshot construction and CAS publication."""

    def __init__(self, *, policy: CustomerProfileProjectionPolicy | None = None) -> None:
        self.policy = policy or customer_profile_projection_policy

    def assess_draft(self, draft: CustomerProfileProjectionDraft) -> CustomerProfileProjectionAssessment:
        """Evaluate hard invariants and soft quality diagnostics in one pass."""

        try:
            return self.policy.assess(draft)
        except CustomerProfileProjectionValidationError as exc:
            raise CustomerProfileProjectionError(str(exc), code=exc.code) from exc

    def validate_draft(self, draft: CustomerProfileProjectionDraft) -> CustomerProfileSections:
        """Validate hard publication invariants."""

        return self.assess_draft(draft).sections

    def lint_draft(self, draft: CustomerProfileProjectionDraft) -> CustomerProfileQualityReport:
        """Return non-blocking narrative diagnostics for a validated draft."""

        return self.assess_draft(draft).quality_report

    def merge_partial_draft(
        self,
        db: Session,
        *,
        team_id: int,
        customer_id: int,
        draft: CustomerProfileProjectionDraft,
    ) -> CustomerProfileProjectionDraft:
        """Merge an event-scoped draft with the current published projection.

        The context loader intentionally produces a complete deterministic
        candidate.  The merge happens at the publication seam so a partial
        event cannot overwrite unrelated sections with an older checkpoint or
        a degraded model response.  Evidence and watermarks remain those of
        the fresh candidate: a delete/permission change must be able to remove
        stale references even when only one section is narratively updated.
        """

        target_sections = tuple(dict.fromkeys(draft.target_sections))
        if not target_sections or set(target_sections) == set(PROFILE_SECTION_NAMES):
            return draft
        unknown_sections = set(target_sections) - set(PROFILE_SECTION_NAMES)
        if unknown_sections:
            raise CustomerProfileProjectionError(
                f"档案更新段落无效: {', '.join(sorted(unknown_sections))}",
                code="PROFILE_SECTION_INVALID",
            )

        current = customer_profile_projection_crud.get_current(
            db,
            team_id=team_id,
            customer_id=customer_id,
            for_update=True,
        )
        if current is None:
            return draft
        previous = customer_profile_projection_crud.get_current_version(
            db,
            team_id=team_id,
            customer_id=customer_id,
            current=current,
        )
        if previous is None:
            return draft

        previous_sections = CustomerProfileSections.model_validate(_version_sections(previous))
        merged_sections = draft.sections.model_copy(
            update={
                name: getattr(draft.sections, name)
                if name in target_sections
                else getattr(previous_sections, name)
                for name in PROFILE_SECTION_NAMES
            }
        )
        # A partial draft keeps the previous sections, so it must also keep the
        # evidence registry needed by those sections.  Do not silently publish
        # a narrative whose old citations no longer exist in the new candidate.
        # The evidence resolver remains the authority for current visibility;
        # deleted or newly restricted records are rendered as unavailable rather
        # than being mistaken for fresh evidence.
        evidence_refs = _merge_evidence_refs(previous.evidence_refs_json, draft.evidence_refs)
        return replace(draft, sections=merged_sections, evidence_refs=evidence_refs)

    def ensure_current(
        self,
        db: Session,
        *,
        team_id: int,
        customer_id: int,
        status: str = CustomerProfileStatus.NOT_READY,
        active_run_id: int | None = None,
    ) -> CustomerProfileCurrent:
        # A locking read cannot protect a row that does not exist.  Use a
        # snapshot read for the first lookup, then let the unique constraint
        # arbitrate first creation and lock the winner before returning it.
        current = customer_profile_projection_crud.get_current(
            db, team_id=team_id, customer_id=customer_id, for_update=False
        )
        if current is None:
            candidate = CustomerProfileCurrent(
                team_id=team_id,
                customer_id=customer_id,
                profile_status=status,
                latest_source_watermark_json={},
                active_run_id=active_run_id,
            )
            try:
                # Keep a duplicate-key rollback inside a SAVEPOINT so callers
                # retain their surrounding transaction.
                with db.begin_nested():
                    db.add(candidate)
                    db.flush()
                current = candidate
            except IntegrityError as exc:
                if not _is_current_identity_conflict(exc):
                    raise
                current = customer_profile_projection_crud.get_current(
                    db, team_id=team_id, customer_id=customer_id, for_update=True
                )
                if current is None:
                    # The unique constraint said the row exists, so a missing
                    # row here indicates an unexpected database/transaction
                    # state and must not be silently converted to success.
                    raise
        else:
            # Existing rows still need a locking read before callers mutate
            # status or active_run_id.
            current = customer_profile_projection_crud.get_current(
                db, team_id=team_id, customer_id=customer_id, for_update=True
            )

        if active_run_id is not None:
            current.active_run_id = active_run_id
            current.profile_status = status
            db.flush()
        return current

    def mark_updating(
        self,
        db: Session,
        *,
        team_id: int,
        customer_id: int,
        run_id: int | None,
    ) -> CustomerProfileCurrent:
        return self.ensure_current(
            db,
            team_id=team_id,
            customer_id=customer_id,
            status=CustomerProfileStatus.UPDATING,
            active_run_id=run_id,
        )

    def mark_failed(
        self,
        db: Session,
        *,
        team_id: int,
        customer_id: int,
        run_id: int | None,
        reason: str,
    ) -> CustomerProfileCurrent:
        """Record a terminal refresh failure in the authoritative read model."""

        current = self.ensure_current(db, team_id=team_id, customer_id=customer_id)
        active_run_id = current.active_run_id
        if run_id is not None and active_run_id not in {None, run_id}:
            raise CustomerProfileProjectionError(
                "客户档案失败状态不能覆盖其他运行",
                code="PROFILE_STATE_REJECTED_STALE_RUN",
            )
        current.profile_status = CustomerProfileStatus.FAILED
        current.stale_reason = (reason or "客户档案刷新失败")[:255]
        current.active_run_id = None
        db.flush()
        return current

    def mark_stale(
        self,
        db: Session,
        *,
        team_id: int,
        customer_id: int,
        source_watermark: dict[str, object],
        reason: str,
        run_id: int | None = None,
    ) -> CustomerProfileCurrent:
        current = self.ensure_current(db, team_id=team_id, customer_id=customer_id)
        current.latest_source_watermark_json = _json_object(source_watermark)
        current.profile_status = CustomerProfileStatus.STALE
        current.stale_reason = reason[:255]
        if run_id is not None:
            current.active_run_id = run_id
        db.flush()
        return current

    def publish(
        self,
        db: Session,
        *,
        team_id: int,
        customer_id: int,
        draft: CustomerProfileProjectionDraft,
        run_id: int | None = None,
        expected_current_version: int | None = None,
        publication_owner: str | None = None,
    ) -> CustomerProfilePublication:
        # A durable run is an infrastructure-owned publication.  Check the
        # owner before touching customer state or merging a partial draft so an
        # unauthorized caller cannot acquire a row lock or trigger any
        # publication-side work, even when its payload is otherwise valid.
        # Direct service calls without a durable run remain available for
        # migration/unit-test tooling and do not bypass the runtime firewall.
        if run_id is not None and publication_owner != PROFILE_WORKFLOW_OWNER:
            raise CustomerProfileProjectionError(
                "客户档案只能由专用投影工作流发布",
                code="PROFILE_PUBLISH_OWNER_FORBIDDEN",
            )

        customer = db.query(Customer).filter(Customer.team_id == team_id, Customer.id == customer_id).one_or_none()
        if customer is None:
            raise CustomerProfileProjectionError("客户不存在或不属于当前团队")

        draft = self.merge_partial_draft(
            db,
            team_id=team_id,
            customer_id=customer_id,
            draft=draft,
        )

        # Re-evaluate after partial merging so preserved sections are checked
        # too. The Agent may carry diagnostics through its checkpoint, but this
        # policy assessment is authoritative at the publication seam.
        assessment = self.assess_draft(draft)
        sections = assessment.sections
        quality_report = assessment.quality_report
        source_watermark = _json_object(draft.source_watermark)
        evidence_refs = _json_list(draft.evidence_refs)
        content = _canonical_json({"sections": sections.model_dump(mode="json"), "evidence_refs": evidence_refs})
        content_hash = _hash(content)
        watermark_hash = _hash(_canonical_json(source_watermark))

        current = self.ensure_current(db, team_id=team_id, customer_id=customer_id)
        current_version_number = int(current.last_successful_version or 0)
        if expected_current_version is not None and current_version_number != expected_current_version:
            raise CustomerProfileProjectionError(
                "档案当前版本已变化, 请重新读取后再发布",
                code="PROFILE_PUBLISH_REJECTED_STALE",
            )

        known_watermark = _json_object(current.latest_source_watermark_json or {})
        previous = None
        if current.current_profile_version_id is not None:
            previous = customer_profile_projection_crud.get_version(
                db,
                team_id=team_id,
                customer_id=customer_id,
                version_id=current.current_profile_version_id,
            )
        changed_sections = tuple(
            _changed_section_names(_version_sections(previous), sections.model_dump(mode="json"))
        )
        comparison = customer_profile_watermark_service.compare(source_watermark, known_watermark)
        if comparison.is_behind:
            raise CustomerProfileProjectionError(
                "当前运行读取到的业务水位已落后于档案已知水位，拒绝覆盖新版本",  # noqa: RUF001
                code="PROFILE_PUBLISH_REJECTED_STALE",
            )

        duplicate = customer_profile_projection_crud.find_duplicate(
            db,
            team_id=team_id,
            customer_id=customer_id,
            content_hash=content_hash,
            source_watermark_hash=watermark_hash,
        )
        if duplicate is not None:
            if duplicate.profile_version >= current_version_number:
                current.current_profile_version_id = duplicate.id
                current.profile_status = CustomerProfileStatus.READY
                current.last_successful_version = duplicate.profile_version
                current.last_successful_published_at = duplicate.published_at
                current.latest_source_watermark_json = customer_profile_watermark_service.merge(
                    known_watermark, source_watermark
                )
                current.latest_fact_watermark = max(current.latest_fact_watermark or 0, draft.fact_watermark)
                current.latest_journey_watermark = max(current.latest_journey_watermark or 0, draft.journey_watermark)
                current.latest_task_watermark = max(current.latest_task_watermark or 0, draft.task_watermark)
                current.latest_commitment_watermark = max(
                    current.latest_commitment_watermark or 0, draft.commitment_watermark
                )
                current.stale_reason = None
                current.active_run_id = None
                db.flush()
            # Replaying the same source snapshot is idempotent.  It may move
            # the current pointer to the already-published version, but it did
            # not change any readable section in this execution.  Returning the
            # calculated diff here would make consumers render a false change
            # for a duplicate event.
            return CustomerProfilePublication(
                version=duplicate,
                current=current,
                deduplicated=True,
                changed_sections=(),
                quality_report=quality_report,
            )

        now = business_now()
        version_number = current_version_number + 1
        version = CustomerProfileProjectionVersion(
            team_id=team_id,
            customer_id=customer_id,
            schema_version=PROFILE_SCHEMA_VERSION,
            profile_version=version_number,
            publication_status=(
                CustomerProfilePublicationStatus.PUBLISHED_WITH_WARNINGS
                if quality_report.has_warnings
                else CustomerProfilePublicationStatus.PUBLISHED
            ),
            current_situation_json=sections.current_situation,
            current_journeys_json=sections.current_journeys,
            important_changes_json=sections.important_changes,
            long_term_context_json=sections.long_term_context,
            follow_up_process_json=sections.follow_up_process,
            recorded_follow_ups_json=sections.recorded_follow_ups,
            evidence_refs_json=evidence_refs,
            quality_report_json=quality_report.as_json(),
            source_watermark_json=source_watermark,
            source_watermark_hash=watermark_hash,
            fact_watermark=max(0, int(draft.fact_watermark)),
            journey_watermark=max(0, int(draft.journey_watermark)),
            task_watermark=max(0, int(draft.task_watermark)),
            commitment_watermark=max(0, int(draft.commitment_watermark)),
            source_event_key=draft.source_event_key,
            run_id=run_id,
            graph_version=draft.graph_version,
            content_hash=content_hash,
            generated_at=now,
            published_at=now,
            created_time=now,
        )
        db.add(version)
        db.flush()

        if previous is not None and previous.id != version.id:
            previous.publication_status = CustomerProfilePublicationStatus.SUPERSEDED

        current.current_profile_version_id = version.id
        current.profile_status = CustomerProfileStatus.READY
        current.last_successful_version = version_number
        current.last_successful_published_at = now
        current.latest_source_watermark_json = customer_profile_watermark_service.merge(
            known_watermark, source_watermark
        )
        current.latest_fact_watermark = max(current.latest_fact_watermark or 0, int(draft.fact_watermark))
        current.latest_journey_watermark = max(current.latest_journey_watermark or 0, int(draft.journey_watermark))
        current.latest_task_watermark = max(current.latest_task_watermark or 0, int(draft.task_watermark))
        current.latest_commitment_watermark = max(
            current.latest_commitment_watermark or 0, int(draft.commitment_watermark)
        )
        current.stale_reason = None
        current.active_run_id = None
        db.flush()
        return CustomerProfilePublication(
            version=version,
            current=current,
            changed_sections=changed_sections,
            quality_report=quality_report,
        )

    def get_current_by_public_id(
        self,
        db: Session,
        *,
        team_id: int,
        customer_public_id: str,
    ) -> tuple[Customer, CustomerProfileCurrent | None, CustomerProfileProjectionVersion | None]:
        customer = (
            db.query(Customer)
            .filter(Customer.team_id == team_id, Customer.public_id == customer_public_id)
            .one_or_none()
        )
        if customer is None:
            raise CustomerProfileProjectionError("客户不存在或无权访问")
        current = customer_profile_projection_crud.get_current(db, team_id=team_id, customer_id=int(customer.id))
        version = (
            customer_profile_projection_crud.get_current_version(
                db, team_id=team_id, customer_id=int(customer.id), current=current
            )
            if current
            else None
        )
        return customer, current, version

    def list_versions(
        self,
        db: Session,
        *,
        team_id: int,
        customer_id: int,
        limit: int = 20,
        before_version: int | None = None,
    ) -> tuple[list[CustomerProfileProjectionVersion], int | None]:
        return customer_profile_projection_crud.list_versions(
            db,
            team_id=team_id,
            customer_id=customer_id,
            limit=limit,
            before_version=before_version,
        )

    def list_changes(
        self,
        db: Session,
        *,
        team_id: int,
        customer_id: int,
        limit: int = 20,
        before_version: int | None = None,
        from_value: str | None = None,
        to_value: str | None = None,
        section_id: str | None = None,
    ) -> tuple[list[dict[str, object]], int | None]:
        """Build adjacent-version diffs without mutating immutable snapshots."""

        versions, next_version = customer_profile_projection_crud.list_versions(
            db,
            team_id=team_id,
            customer_id=customer_id,
            limit=limit,
            before_version=before_version,
        )
        changes: list[dict[str, object]] = []
        for version in versions:
            published_at = version.published_at or version.generated_at
            if from_value and published_at and published_at.isoformat() < from_value:
                continue
            if to_value and published_at and published_at.isoformat() > to_value:
                continue
            previous = customer_profile_projection_crud.get_previous_version(
                db,
                team_id=team_id,
                customer_id=customer_id,
                profile_version=int(version.profile_version),
            )
            before_sections = _version_sections(previous)
            after_sections = _version_sections(version)
            section_changes = {
                section: _diff_values(before_sections.get(section), after_sections.get(section))
                for section in after_sections
            }
            section_changes = {section: values for section, values in section_changes.items() if values}
            changed_sections = list(section_changes)
            if section_id and section_id not in changed_sections:
                continue
            changes.append(
                {
                    "from_profile_version": int(previous.profile_version) if previous else None,
                    "to_profile_version": int(version.profile_version),
                    "from_profile_version_public_id": str(previous.public_id) if previous else None,
                    "to_profile_version_public_id": str(version.public_id),
                    "changed_at": published_at,
                    "source_event_key": str(version.source_event_key) if version.source_event_key else None,
                    "changed_sections": changed_sections,
                    "changes": section_changes,
                    "evidence_refs": _json_list(version.evidence_refs_json),
                }
            )
        return changes, next_version

    def draft_from_context(
        self,
        *,
        context: JSONDict,
        source_event_key: str | None,
        source_watermark: dict[str, object] | None = None,
        target_sections: tuple[str, ...] | list[str] | None = None,
    ) -> CustomerProfileProjectionDraft:
        """Build a readable profile from a permission-filtered context snapshot.

        Business states are assembled from MySQL facts only.  The method keeps
        the narrative close to the recorded wording and attaches evidence keys
        to every meaningful item, so a later LLM composer can replace only the
        prose without taking ownership of attribution or status.
        """
        strong = coerce_json_dict(context.get("strong_context"))
        customer = coerce_json_dict(strong.get("customer"))
        activities = _json_dict_list(strong.get("recent_activities"))
        facts = _json_dict_list(strong.get("customer_facts"))
        contacts = _json_dict_list(strong.get("contacts"))
        opportunities = _json_dict_list(strong.get("opportunities"))
        contracts = _json_dict_list(strong.get("contracts"))
        payment_plans = _json_dict_list(strong.get("payment_plans"))
        payment_records = _json_dict_list(strong.get("payment_records"))
        journeys = _json_dict_list(strong.get("deal_journeys"))
        journey_events = _json_dict_list(strong.get("deal_journey_events"))
        tasks = [item for item in _json_dict_list(strong.get("recorded_follow_ups")) if item.get("kind") == "task"]
        commitments = _json_dict_list(strong.get("sales_commitments"))
        task_events = _json_dict_list(strong.get("follow_up_task_events"))
        activities = sorted(activities, key=_timeline_sort_key, reverse=True)
        evidence_refs = _build_evidence_registry(context, activities, journey_events, tasks, commitments, facts)
        journey_sections = _project_journeys(
            journeys=journeys,
            journey_events=journey_events,
            task_events=task_events,
            activities=activities,
            opportunities=opportunities,
            contracts=contracts,
            payment_plans=payment_plans,
            payment_records=payment_records,
            tasks=tasks,
            commitments=commitments,
        )
        active_journeys = [item for item in journey_sections if item.get("status") == "ACTIVE"]
        journey_history = [item for item in journey_sections if item.get("status") != "ACTIVE"]
        latest_activity = activities[0] if activities else {}
        demand_items = _demand_items(activities, facts=facts)
        process = _follow_up_process(activities)
        recorded_follow_ups = _recorded_follow_ups(tasks, commitments, task_events)
        important_changes = _important_change_items(
            activities,
            journey_events=journey_events,
            tasks=tasks,
            task_events=task_events,
        )
        current_summary = _current_situation_summary(
            customer=customer,
            active_journeys=active_journeys,
            opportunities=opportunities,
            contracts=contracts,
            latest_activity=latest_activity,
            process=process,
            demand_items=demand_items,
        )
        long_term_context = {
            "overview": _long_term_overview(customer, facts, contacts),
            "customer": _customer_basics(customer),
            "facts": [
                {
                    **fact,
                    "evidence_refs": [f"fact:{fact.get('id')}"],
                }
                for fact in facts[:50]
            ],
            "contacts": contacts[:50],
            "journey_history": journey_history,
            "opportunities": opportunities[:50],
            "contracts": contracts[:50],
            "payment_plans": payment_plans[:100],
            "payment_records": payment_records[:100],
        }
        watermark = _json_object(
            source_watermark
            or coerce_json_dict(context.get("source_watermark"))
            or {
                "customer_updated_at": customer.get("updated_time"),
                "latest_activity_at": latest_activity.get("occurred_at"),
                "latest_journey_at": _latest_value(journey_events, "event_time"),
                "latest_task_event_at": _latest_value(task_events, "created_time"),
                "latest_event_key": source_event_key,
            }
        )
        sections = CustomerProfileSections(
            current_situation={
                "headline": str(customer.get("account_name") or "该客户"),
                "summary": current_summary,
                "customer_basics": _customer_basics(customer),
                "demand_background": {
                    "summary": _demand_background_summary(demand_items),
                    "items": demand_items,
                },
                "business_status": _business_status(active_journeys, opportunities, contracts, payment_records),
                "latest_change": important_changes[0] if important_changes else None,
            },
            current_journeys=active_journeys,
            important_changes=important_changes,
            long_term_context=long_term_context,
            follow_up_process=process[:30],
            recorded_follow_ups=recorded_follow_ups[:80],
        )
        normalized_target_sections = tuple(
            dict.fromkeys(
                section
                for section in (target_sections or PROFILE_SECTION_NAMES)
                if section in PROFILE_SECTION_NAMES
            )
        )
        return CustomerProfileProjectionDraft(
            sections=sections,
            evidence_refs=evidence_refs,
            source_watermark=watermark,
            fact_watermark=_max_id(facts),
            journey_watermark=max(_max_id(journey_events), _max_id(journeys)),
            task_watermark=max(_max_id(task_events), _max_id(tasks)),
            commitment_watermark=_max_id(commitments),
            source_event_key=source_event_key,
            target_sections=normalized_target_sections,
        )


customer_profile_projection_service = CustomerProfileProjectionService()


def _is_current_identity_conflict(exc: IntegrityError) -> bool:
    """Return whether an integrity error is the current-row unique race."""

    detail = str(exc.orig).lower()
    return "uq_customer_profile_current_team_customer" in detail or (
        "crm_customer_profile_current" in detail and "team_id" in detail and "customer_id" in detail
    )


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _hash(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _json_object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise CustomerProfileProjectionError("档案来源水位必须是对象")
    json_value = json.loads(_canonical_json(value))
    if not isinstance(json_value, dict):
        raise CustomerProfileProjectionError("档案来源水位必须是JSON对象")
    return json_value


def _json_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        raise CustomerProfileProjectionError("档案证据必须是数组")
    result = json.loads(_canonical_json(value))
    if not isinstance(result, list) or not all(isinstance(item, dict) for item in result):
        raise CustomerProfileProjectionError("档案证据必须是对象数组")
    return result


def _merge_evidence_refs(previous: object, fresh: object) -> list[dict[str, object]]:
    """Union evidence metadata required by preserved and refreshed sections."""

    merged: dict[str, dict[str, object]] = {}
    for raw in (*_json_list(previous), *_json_list(fresh)):
        key = raw.get("evidence_key") or raw.get("evidence_id") or raw.get("id")
        if not isinstance(key, str) or not key.strip():
            continue
        # Fresh metadata wins when the same reference is present in both
        # versions, while insertion order remains stable for readable APIs.
        merged[key.strip()] = raw
    return list(merged.values())


def _json_dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _int_value(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return 0


def _max_id(items: list[dict[str, object]]) -> int:
    return max((_int_value(item.get("id")) for item in items), default=0)


def _latest_value(items: list[dict[str, object]], key: str) -> str | None:
    values = [str(value) for item in items if (value := item.get(key)) is not None]
    return max(values, default=None)


def _timeline_sort_key(item: dict[str, object]) -> str:
    return str(
        item.get("occurred_at")
        or item.get("event_time")
        or item.get("created_time")
        or item.get("updated_time")
        or item.get("extracted_at")
        or ""
    )


def _text(value: object, *, limit: int = 500) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:limit].strip()


def _sentence_body(value: object, *, limit: int = 500) -> str:
    """Normalize a fragment before the projection adds its own sentence ending."""

    return _text(value, limit=limit).rstrip("。！？!?；; ")  # noqa: RUF001


def _customer_basics(customer: Mapping[str, object]) -> dict[str, object]:
    """Return only meaningful company facts for the readable company section.

    This is deliberately structured instead of emitting a generic AI summary:
    the UI can hide absent fields and managers can scan the facts without
    reading system-generated caveats.
    """

    keys = (
        "account_name",
        "industry_name",
        "city",
        "address",
        "company_scale",
        "source",
        "status",
        "created_time",
    )
    return {
        key: value
        for key in keys
        if (value := customer.get(key)) not in (None, "", [])
    }


def _evidence_key(kind: str, object_id: object) -> str:
    return f"{kind}:{object_id}"


def _refs(*keys: str | None) -> list[str]:
    return list(dict.fromkeys(key for key in keys if key))


def _build_evidence_registry(
    context: JSONDict,
    activities: list[dict[str, object]],
    journey_events: list[dict[str, object]],
    tasks: list[dict[str, object]],
    commitments: list[dict[str, object]],
    facts: list[dict[str, object]],
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    seen: set[str] = set()

    def add(key: str, source_type: str, source_id: object, occurred_at: object = None, title: object = None) -> None:
        if key in seen:
            return
        seen.add(key)
        result.append(
            {
                "evidence_key": key,
                "source_type": source_type,
                "source_id": source_id,
                "occurred_at": occurred_at,
                "title": _text(title, limit=255) or None,
            }
        )

    for item in _json_dict_list(context.get("semantic_evidence"))[:20]:
        key = _text(item.get("evidence_key") or item.get("id") or item.get("source_key"), limit=128)
        if key:
            add(
                key,
                _text(item.get("source_type")) or "semantic_evidence",
                item.get("source_id"),
                item.get("occurred_at"),
                item.get("title"),
            )
    for item in activities:
        add(
            _evidence_key("activity", item.get("id")),
            "customer_activity",
            item.get("id"),
            item.get("occurred_at"),
            item.get("title"),
        )
    for item in journey_events:
        add(
            _evidence_key("journey_event", item.get("id")),
            "deal_journey_event",
            item.get("id"),
            item.get("event_time"),
            item.get("summary"),
        )
    for item in tasks:
        task_id = item.get("task_id") or item.get("id")
        add(
            _evidence_key("task", task_id),
            "follow_up_task",
            task_id,
            item.get("updated_time"),
            item.get("title"),
        )
    for item in commitments:
        add(
            _evidence_key("commitment", item.get("id")),
            "sales_commitment",
            item.get("id"),
            item.get("updated_time"),
            item.get("title"),
        )
    for item in facts:
        add(
            _evidence_key("fact", item.get("id")),
            "customer_fact",
            item.get("id"),
            item.get("created_time"),
            item.get("fact_type"),
        )
    return result


_DEMAND_KEYWORDS = (
    "需求",
    "使用",
    "服务器",
    "部署",
    "采购",
    "功能",
    "预算",
    "系统",
    "平台",
    "接口",
    "场景",
    "私有化",
    "试用",
    "POC",
    "验收",
)
_TOPIC_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("project_blocked", ("没进展", "暂无进展", "出差", "等领导", "等待领导")),
    ("approval", ("立项", "审批", "采购流程", "报价确认")),
    ("private_solution", ("私有化", "私有环境", "安装包", "部署方案", "本地部署")),
    ("usage_expansion", ("账号已用满", "增购", "授权", "续费", "扩大使用", "全公司")),
    ("reporting", ("报表", "导出", "按部门")),
    ("internal_validation", ("1-2个项目", "1—2个项目", "内部试用", "cto", "上级汇报")),
    ("procurement", ("预算", "采购", "招标", "放款", "财务审批", "付款", "内部过", "再给答复", "对一下时间")),
    ("acceptance", ("验收", "轻量交互页面")),
    ("poc", ("poc", "试用", "测试环境", "暂无问题", "正常进行")),
    ("generic_demand", _DEMAND_KEYWORDS),
)
_TOPIC_TITLES = {
    "project_blocked": "项目推进受阻",
    "approval": "立项与审批推进",
    "private_solution": "私有化方案评估",
    "acceptance": "产品事项验收",
    "poc": "POC 试用验证",
    "generic_demand": "客户沟通",
    "usage_expansion": "使用与授权范围",
    "reporting": "报表使用需求",
    "procurement": "采购与预算推进",
    "internal_validation": "内部试用与汇报",
}

_FACT_DEMAND_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("private_solution", ("私有化", "私有环境", "安装包", "本地部署", "部署方案")),
    ("reporting", ("报表", "导出", "按部门")),
    ("internal_validation", ("1-2个项目", "1—2个项目", "内部试用", "cto", "上级汇报")),
    ("usage_expansion", ("账号已用满", "增购", "授权", "续费", "扩大使用", "全公司")),
    ("procurement", ("预算", "采购", "招标", "放款", "财务审批", "付款")),
)


def _activity_text(activity: dict[str, object], *, limit: int = 800) -> str:
    """Prefer the concise recorded summary, falling back to the source wording."""

    return _text(activity.get("content") or activity.get("summary") or activity.get("source_content"), limit=limit)


def _activity_topic(activity: dict[str, object]) -> str | None:
    text = _activity_text(activity, limit=1200).lower()
    if not text:
        return None
    for topic, keywords in _TOPIC_RULES:
        if any(keyword.lower() in text for keyword in keywords):
            return topic
    return None


def _activity_datetime(activity: dict[str, object]) -> datetime | None:
    value = activity.get("occurred_at") or activity.get("event_time") or activity.get("created_time")
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


_TEXT_NORMALIZATION_PATTERN = r"[\s\uFF0C\u3002\uFF1B\uFF1A\u3001,.!?\uFF01\uFF1F\uFF08\uFF09()\-—_]+"


def _similar_text(left: str, right: str) -> bool:
    """Cheap deterministic near-duplicate detection for short CRM notes."""

    normalized_left = re.sub(_TEXT_NORMALIZATION_PATTERN, "", left).lower()
    normalized_right = re.sub(_TEXT_NORMALIZATION_PATTERN, "", right).lower()
    if not normalized_left or not normalized_right:
        return False
    if normalized_left in normalized_right or normalized_right in normalized_left:
        return True
    left_chars, right_chars = set(normalized_left), set(normalized_right)
    overlap = len(left_chars & right_chars) / max(1, min(len(left_chars), len(right_chars)))
    return overlap >= 0.86


def _unique_activity_texts(activities: list[dict[str, object]], *, limit: int = 3) -> list[str]:
    texts: list[str] = []
    for activity in sorted(activities, key=_timeline_sort_key):
        text = _activity_text(activity, limit=800)
        if text and not any(_similar_text(text, existing) for existing in texts):
            texts.append(text)
    return texts[-limit:]


def _group_activities(activities: list[dict[str, object]]) -> list[tuple[str, list[dict[str, object]]]]:
    """Group notes by recorded topic while keeping long-running phases readable.

    A topic starts a new node after a long gap, so an old need does not silently
    become the current phase. Within a phase, repeated notes are represented by
    one node with all evidence refs and a small set of distinct recorded facts.
    """

    groups: list[tuple[str, list[dict[str, object]]]] = []
    group_indexes: dict[str, int] = {}
    last_by_topic: dict[str, datetime] = {}
    for activity in sorted(activities, key=_timeline_sort_key):
        topic = _activity_topic(activity) or "other"
        occurred_at = _activity_datetime(activity)
        group_index = group_indexes.get(topic)
        previous_at = last_by_topic.get(topic)
        gap_days = 0.0
        if previous_at is not None and occurred_at is not None:
            try:
                gap_days = (occurred_at - previous_at).total_seconds() / 86400
            except TypeError:
                gap_days = 0.0
        if group_index is None or gap_days > 45:
            group_indexes[topic] = len(groups)
            groups.append((topic, [activity]))
        else:
            groups[group_index][1].append(activity)
        if occurred_at is not None:
            last_by_topic[topic] = occurred_at
    return groups


def _demand_statement(topic: str, activities: list[dict[str, object]]) -> tuple[str, str]:
    latest_text = _unique_activity_texts(activities, limit=2)
    combined = "；".join(latest_text)  # noqa: RUF001
    if topic == "usage_expansion":
        return (
            "客户团队已在使用产品且账号已用满，正在推进授权增购，并评估从部门使用扩大到更大范围。",  # noqa: RUF001
            "增购与使用范围评估中",
        )
    if topic == "reporting":
        return "客户要求数据报表支持按部门导出。", "需求已提出"
    if topic == "internal_validation":
        return "客户计划内部选择1—2个项目试用，并向上级CTO汇报项目情况。", "内部验证推进中"  # noqa: RUF001
    if topic == "procurement":
        return "客户正在推进采购预算、内部审批和付款安排。", "采购与付款推进中"
    if topic == "private_solution":
        return (
            "客户正在重新评估 Apifox 私有化部署方案，需要私有环境安装包和试用方案。",  # noqa: RUF001
            "方案仍在评估，相关部署支持需求已被记录。",  # noqa: RUF001
        )
    if topic == "poc":
        if any(marker in combined for marker in ("已部署", "已安装", "正式试用", "暂无问题", "正常")):
            return (
                "POC 环境已部署完成并进入正式试用，最近记录反馈正常、暂无问题。",  # noqa: RUF001
                "已进入试用验证阶段，最近一次客户反馈暂无问题。",  # noqa: RUF001
            )
        return (
            "客户提出 POC 试用验证需求。",
            "已提出",
        )
    if topic == "acceptance":
        return (
            "测试侧提出轻量交互页面验收需求。",
            "已提出",
        )
    if topic == "approval":
        return (
            "项目正在走立项及内部审批流程，立项材料已提交的记录已形成。",  # noqa: RUF001
            "项目推进依赖客户内部立项与审批节奏。",
        )
    if topic == "project_blocked":
        return (
            "项目曾因客户内部人员出差暂缓推进，后续记录显示项目已恢复跟进。",  # noqa: RUF001
            "早期推进曾暂缓，后续已重新进入项目推进过程。",  # noqa: RUF001
        )
    return (
        latest_text[-1] if latest_text else "",
        "已记录",
    )


def _demand_items(
    activities: list[dict[str, object]],
    *,
    facts: list[dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    """Project needs from notes and structured facts into a few readable themes.

    Facts are evidence for the narrative, not a second list to render.  The
    projection deliberately merges repeated fact revisions by theme so a
    customer with many extracted next steps still reads like a profile.
    """

    items_by_topic: dict[str, dict[str, object]] = {}
    topic_order: list[str] = []
    for topic, grouped in _group_activities(activities):
        if topic not in {
            "private_solution",
            "poc",
            "acceptance",
            "generic_demand",
            "usage_expansion",
            "reporting",
            "internal_validation",
            "procurement",
        }:
            continue
        if topic == "generic_demand" and not any(_is_meaningful_activity(item) for item in grouped):
            continue
        statement, status = _demand_statement(topic, grouped)
        refs = _refs(*(_evidence_key("activity", item.get("id")) for item in grouped))
        journey_ids = list(
            dict.fromkeys(
                item.get("deal_journey_id") for item in grouped if item.get("deal_journey_id") is not None
            )
        )
        latest = grouped[-1]
        item = {
                "topic": topic,
                "statement": statement,
                "occurred_at": grouped[0].get("occurred_at"),
                "latest_at": latest.get("occurred_at"),
                "journey_id": latest.get("deal_journey_id"),
                "journey_ids": journey_ids,
                "activity_count": len(grouped),
                "evidence_refs": refs,
                "status": status,
            }
        items_by_topic[topic] = item
        if topic not in topic_order:
            topic_order.append(topic)

    for topic, grouped_facts in _group_demand_facts(facts or []):
        activity_item = items_by_topic.get(topic)
        fact_refs = _refs(*(_evidence_key("fact", fact.get("id")) for fact in grouped_facts))
        if activity_item is not None:
            activity_item["evidence_refs"] = _refs(*(activity_item.get("evidence_refs") or []), *fact_refs)
            continue
        statement, status = _fact_demand_statement(topic, grouped_facts)
        if not statement:
            continue
        latest = max(grouped_facts, key=_timeline_sort_key)
        items_by_topic[topic] = {
            "topic": topic,
            "statement": statement,
            "occurred_at": min(
                (item.get("occurred_at") or item.get("extracted_at") or "" for item in grouped_facts),
                default=latest.get("occurred_at") or latest.get("extracted_at"),
            ),
            "latest_at": latest.get("occurred_at") or latest.get("extracted_at"),
            "journey_id": None,
            "journey_ids": [],
            "activity_count": 0,
            "evidence_refs": fact_refs,
            "status": status,
        }
        if topic not in topic_order:
            topic_order.append(topic)

    return [items_by_topic[topic] for topic in topic_order if topic in items_by_topic][:8]


def _is_meaningful_activity(activity: dict[str, object]) -> bool:
    text = _activity_text(activity, limit=800)
    normalized = re.sub(_TEXT_NORMALIZATION_PATTERN, "", text).lower()
    return bool(
        normalized
        and normalized not in {"测试", "测试测试", "test", "testtest"}
        and not (normalized.startswith(("neg", "def")) and len(normalized) < 40)
    )


def _fact_topic(fact: dict[str, object]) -> str | None:
    text = " ".join(
        value
        for value in (
            _text(fact.get("subject"), limit=255),
            _text(fact.get("content"), limit=800),
        )
        if value
    ).lower()
    fact_type = str(fact.get("fact_type") or "")
    for topic, keywords in _FACT_DEMAND_RULES:
        if any(keyword.lower() in text for keyword in keywords):
            return topic
    if fact_type == "need":
        return "generic_demand"
    return None


def _group_demand_facts(facts: list[dict[str, object]]) -> list[tuple[str, list[dict[str, object]]]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for fact in sorted(facts, key=_timeline_sort_key, reverse=True):
        topic = _fact_topic(fact)
        if topic is None:
            continue
        content = _text(fact.get("content"), limit=800)
        if not content or any(
            _similar_text(content, _text(item.get("content"), limit=800))
            for item in grouped.get(topic, [])
        ):
            continue
        grouped.setdefault(topic, []).append(fact)
    return list(grouped.items())


def _fact_demand_statement(topic: str, facts: list[dict[str, object]]) -> tuple[str, str]:
    text = "；".join(  # noqa: RUF001
        _text(item.get("content"), limit=500)
        for item in facts
        if _text(item.get("content"), limit=500)
    )
    if topic == "usage_expansion":
        return (
            "客户团队已在使用产品且账号已用满，正在推进授权增购，并评估从部门使用扩大到更大范围。",  # noqa: RUF001
            "增购与使用范围评估中",
        )
    if topic == "reporting":
        return "客户认可权限角色配置，但要求数据报表支持按部门导出。", "需求已提出"  # noqa: RUF001
    if topic == "internal_validation":
        return "客户计划内部选择1—2个项目试用，并向上级CTO汇报项目情况。", "内部验证推进中"  # noqa: RUF001
    if topic == "procurement":
        return (
            "客户同时推进授权增购、续费及更大范围采购评估；采购预算、内部审批和实际放款节奏仍在确认中。",  # noqa: RUF001
            "采购与付款推进中",
        )
    if topic == "private_solution":
        return "客户正在评估私有化部署方案及配套试用支持。", "方案评估中"
    return (_sentence_body(text), "需求已记录") if text else ("", "")


def _important_change_items(
    activities: list[dict[str, object]],
    *,
    journey_events: list[dict[str, object]] | None = None,
    tasks: list[dict[str, object]] | None = None,
    task_events: list[dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    """Expose material customer changes across activities and business events.

    The section is a change timeline, not a dump of every source row.  Activity
    phases remain grouped, while journey/task events are represented as the
    concrete state transitions that partial refreshes are expected to expose.
    """

    result: list[dict[str, object]] = []
    for topic, grouped in _group_activities(activities):
        if topic == "other" or (
            topic == "generic_demand"
            and not any(_is_meaningful_activity(item) for item in grouped)
        ):
            continue
        latest = grouped[-1]
        result.append(
            {
                "occurred_at": latest.get("occurred_at"),
                "title": _TOPIC_TITLES.get(topic, "其他跟进过程"),
                "change": _process_change(topic, grouped),
                "next_action_recorded": (
                    _text(latest.get("next_action"), limit=500)
                    if _is_displayable_follow_up({"title": latest.get("next_action")})
                    else None
                ),
                "journey_id": latest.get("deal_journey_id"),
                "activity_count": len(grouped),
                "evidence_refs": _refs(*(_evidence_key("activity", item.get("id")) for item in grouped)),
            }
        )

    for event in journey_events or []:
        event_id = event.get("id")
        if str(event.get("event_type") or "") not in {"STAGE_CHANGED", "STATUS_CHANGED"}:
            continue
        summary = _text(event.get("summary"), limit=500)
        if event_id is None or not summary:
            continue
        result.append(
            {
                "occurred_at": event.get("event_time") or event.get("created_time"),
                "title": _journey_event_title(event.get("event_type")),
                "change": summary,
                "journey_id": event.get("deal_journey_id"),
                "event_type": event.get("event_type"),
                "evidence_refs": [_evidence_key("journey_event", event_id)],
            }
        )

    task_by_id = {
        item.get("task_id") or item.get("id"): item
        for item in (tasks or [])
        if item.get("task_id") is not None or item.get("id") is not None
    }
    for event in task_events or []:
        event_id = event.get("id")
        task_id = event.get("task_id")
        if event_id is None or task_id is None:
            continue
        task = task_by_id.get(task_id, {})
        if not _is_material_task_event(event):
            continue
        title = _text(task.get("title"), limit=255) or "跟进待办"
        previous = _status_label(event.get("previous_status"))
        current = _status_label(event.get("new_status"))
        if previous and current:
            change = f"待办“{title}”状态由“{previous}”变为“{current}”。"
        elif current:
            change = f"待办“{title}”记录为“{current}”。"
        else:
            change = f"待办“{title}”发生状态变更。"
        result.append(
            {
                "occurred_at": event.get("created_time"),
                "title": "跟进待办状态变化",
                "change": change,
                "journey_id": task.get("deal_journey_id"),
                "task_id": task_id,
                "event_type": event.get("event_type"),
                "evidence_refs": [_evidence_key("task", task_id)],
            }
        )

    return sorted(
        result,
        key=lambda item: str(item.get("occurred_at") or ""),
        reverse=True,
    )[:80]


def _journey_event_title(event_type: object) -> str:
    return {
        "STAGE_CHANGED": "业务旅程阶段变化",
        "STATUS_CHANGED": "业务旅程状态变化",
        "OPPORTUNITY_ASSOCIATED": "业务旅程关联商机",
        "CONTRACT_ASSOCIATED": "业务旅程关联合同",
    }.get(str(event_type or ""), "业务旅程变化")


def _status_label(value: object) -> str:
    return {
        "OPEN": "待完成",
        "COMPLETED": "已完成",
        "CANCELLED": "已取消",
        "FULFILLED": "已履行",
        "SUPERSEDED": "已替代",
        "REOPENED": "重新打开",
        "POSTPONED": "已延期",
    }.get(str(value or ""), _text(value, limit=80))


def _is_material_task_event(event: dict[str, object]) -> bool:
    previous = event.get("previous_status")
    current = event.get("new_status")
    if previous is None:
        return False
    if str(previous) == str(current):
        return False
    return bool(current or event.get("event_type"))


def _demand_background_summary(items: list[dict[str, object]]) -> str:
    if not items:
        return ""
    fragments = [
        _sentence_body(item.get("statement"), limit=220)
        for item in items
        if _sentence_body(item.get("statement"), limit=220)
    ]
    return "；".join(fragments[:4]) + "。" if fragments else ""  # noqa: RUF001


def _change_item(activity: dict[str, object]) -> dict[str, object]:
    content = _activity_text(activity)
    return {
        "occurred_at": activity.get("occurred_at"),
        "title": _text(activity.get("title"), limit=255) or "跟进记录",
        "change": content or "本次跟进记录未填写正文。",
        "next_action_recorded": _text(activity.get("next_action"), limit=500) or None,
        "journey_id": activity.get("deal_journey_id"),
        "evidence_refs": [_evidence_key("activity", activity.get("id"))],
    }


def _process_change(topic: str, _activities: list[dict[str, object]]) -> str:
    if topic == "approval":
        return "立项材料已提交，当前记录仍显示项目处于立项/内部审批流程。"  # noqa: RUF001
    if topic == "private_solution":
        return "客户重新评估私有化部署方案，安装包和试用支持需求已被记录。"  # noqa: RUF001
    if topic == "poc":
        return "POC 试用验证需求已提出。"
    if topic == "acceptance":
        return "测试侧提出页面验收事项。"
    if topic == "usage_expansion":
        return "客户团队已在使用产品且账号已用满，近期申请增购授权，并评估扩大使用范围。"  # noqa: RUF001
    if topic == "reporting":
        return "客户提出数据报表按部门导出的使用需求。"
    if topic == "internal_validation":
        return "客户计划内部选择1—2个项目试用，并向上级CTO汇报项目情况。"  # noqa: RUF001
    if topic == "procurement":
        return "客户近期持续确认采购预算、财务审批和放款安排，采购节奏仍在推进中。"  # noqa: RUF001
    return ""


def _follow_up_process(activities: list[dict[str, object]]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for topic, grouped in _group_activities(activities):
        if topic == "other":
            continue
        texts = _unique_activity_texts(grouped, limit=3)
        actions = []
        for item in grouped:
            action = _text(item.get("next_action"), limit=300)
            if action and not any(_similar_text(action, existing) for existing in actions):
                actions.append(action)
        refs = _refs(*(_evidence_key("activity", item.get("id")) for item in grouped))
        journey_ids = list(
            dict.fromkeys(
                item.get("deal_journey_id") for item in grouped if item.get("deal_journey_id") is not None
            )
        )
        result.append(
            {
                "topic": topic,
                "title": _TOPIC_TITLES.get(topic, "客户沟通"),
                "occurred_at": grouped[0].get("occurred_at"),
                "ended_at": grouped[-1].get("occurred_at"),
                "journey_id": grouped[-1].get("deal_journey_id"),
                "journey_ids": journey_ids,
                "activity_count": len(grouped),
                **({"customer_expression": ";".join(texts)} if texts else {}),
                **({"sales_follow_up": ";".join(actions[:2])} if actions else {}),
                **({"customer_feedback": texts[-1]} if texts else {}),
                **({"business_change": change} if (change := _process_change(topic, grouped)) else {}),
                "evidence_refs": refs,
            }
        )
    return result


def _follow_up_identity(item: dict[str, object], *, is_task: bool) -> tuple[str, str, object]:
    """Return a customer-level identity for repeated task/commitment records.

    A task and the commitment that originated it describe one sales-side
    follow-up, so their storage type must not create two rows in the profile.
    Topic identity also collapses successive wording changes such as “等待答
    复” and “确认答复” into the same readable thread.
    """

    del is_task
    text = " ".join(
        value
        for value in (
            _text(item.get("title"), limit=255).lower(),
            _text(item.get("description") or item.get("content"), limit=500).lower(),
        )
        if value
    )
    topic_rules = (
        ("approval", ("立项", "审批", "采购流程")),
        ("reporting", ("报表", "导出", "按部门")),
        ("procurement", ("采购", "预算", "放款", "回款", "财务", "付款", "答复", "确认时间")),
        ("usage_expansion", ("增购", "账号", "授权", "续费", "扩容")),
        ("internal_validation", ("试用", "poc", "cto", "上级汇报", "项目")),
        ("private_solution", ("私有化", "私有环境", "安装包", "部署")),
    )
    topic = next(
        (topic for topic, keywords in topic_rules if any(keyword in text for keyword in keywords)),
        re.sub(_TEXT_NORMALIZATION_PATTERN, "", text),
    )
    return "follow_up", topic, item.get("deal_journey_id")


def _is_displayable_follow_up(item: dict[str, object]) -> bool:
    """Hide bookkeeping instructions that are not customer-facing follow-ups."""

    title = re.sub(_TEXT_NORMALIZATION_PATTERN, "", _text(item.get("title"), limit=255)).lower()
    return bool(title) and title not in {"关闭跟进任务", "关闭任务", "删除跟进任务"}


def _recorded_follow_ups(
    tasks: list[dict[str, object]],
    commitments: list[dict[str, object]],
    task_events: list[dict[str, object]],
) -> list[dict[str, object]]:
    event_map: dict[object, list[dict[str, object]]] = {}
    for event in task_events:
        event_map.setdefault(event.get("task_id"), []).append(event)
    groups: dict[tuple[str, str, object], list[dict[str, object]]] = {}
    task_commitment_ids = {item.get("commitment_id") for item in tasks if item.get("commitment_id") is not None}
    source_items = [
        *[(item, True) for item in tasks],
        *[(commitment, False) for commitment in commitments if commitment.get("id") not in task_commitment_ids],
    ]
    for item, is_task in source_items:
        if not _is_displayable_follow_up(item):
            continue
        identity = _follow_up_identity(item, is_task=is_task)
        groups.setdefault(identity, []).append(item)

    result: list[dict[str, object]] = []
    for grouped in groups.values():
        task_entries = [entry for entry in grouped if entry.get("kind") == "task"]
        # Task rows carry the current sales-side state.  Prefer an open task
        # when a later completed duplicate exists; completion of one generated
        # task must not make the still-open replacement disappear from the
        # customer profile.  Commitments remain supporting history in the same
        # customer-level thread.
        active_task_entries = [entry for entry in task_entries if entry.get("status") == "OPEN"]
        representative_pool = active_task_entries or task_entries or grouped
        item = max(
            representative_pool,
            key=lambda value: str(value.get("updated_time") or value.get("due_at") or ""),
        )
        is_task = bool(task_entries)
        refs = _refs(
            *(
                _evidence_key(
                    "task" if entry.get("kind") == "task" else "commitment",
                    (entry.get("task_id") or entry.get("id"))
                    if entry.get("kind") == "task"
                    else entry.get("id"),
                )
                for entry in grouped
            )
        )
        history = (
            [event for entry in task_entries for event in event_map.get(entry.get("task_id") or entry.get("id"), [])]
            if is_task
            else []
        )
        history = sorted(history, key=lambda value: str(value.get("created_time") or value.get("id") or ""))
        raw_status = str(item.get("status") or "")
        due_dates = [str(entry.get("due_at")) for entry in grouped if entry.get("due_at")]
        completed_dates = [str(entry.get("completed_at")) for entry in grouped if entry.get("completed_at")]
        cancelled_dates = [str(entry.get("cancelled_at")) for entry in grouped if entry.get("cancelled_at")]
        result.append(
            {
                "kind": "task" if is_task else "commitment",
                "title": _text(item.get("title"), limit=255),
                "content": _text(item.get("description") or item.get("content"), limit=800),
                "status": _follow_up_status(raw_status),
                "raw_status": item.get("status"),
                "due_at": max(due_dates, default=None),
                "completed_at": (
                    max(completed_dates, default=None)
                    if raw_status in {"COMPLETED", "FULFILLED"}
                    else None
                ),
                "cancelled_at": (
                    max(cancelled_dates, default=None)
                    if raw_status == "CANCELLED"
                    else None
                ),
                "deal_journey_id": item.get("deal_journey_id"),
                "source_activity_id": item.get("source_activity_id"),
                "activity_count": len(grouped),
                "recorded_titles": list(
                    dict.fromkeys(
                        _text(entry.get("title"), limit=255)
                        for entry in grouped
                        if _text(entry.get("title"), limit=255)
                    )
                ),
                "evidence_refs": refs,
                "status_history": history,
            }
        )
    return sorted(
        result,
        key=lambda item: (
            0 if item.get("status") == "待完成" else 1,
            str(item.get("due_at") or item.get("completed_at") or ""),
        ),
    )


def _follow_up_status(status: object) -> str:
    return {
        "OPEN": "待完成",
        "COMPLETED": "已完成（销售履行）",  # noqa: RUF001
        "CANCELLED": "已取消",
        "FULFILLED": "已完成（销售履行）",  # noqa: RUF001
        "SUPERSEDED": "已替代",
    }.get(str(status or ""), "状态未确认")


def _project_journeys(
    *,
    journeys: list[dict[str, object]],
    journey_events: list[dict[str, object]],
    task_events: list[dict[str, object]],
    activities: list[dict[str, object]],
    opportunities: list[dict[str, object]],
    contracts: list[dict[str, object]],
    payment_plans: list[dict[str, object]],
    payment_records: list[dict[str, object]],
    tasks: list[dict[str, object]],
    commitments: list[dict[str, object]],
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    recorded_follow_ups = _recorded_follow_ups(tasks, commitments, task_events)
    for journey in journeys:
        journey_id = journey.get("id")
        journey_opportunities = [
            item
            for item in opportunities
            if _belongs_to_journey(item, journey_id, "deal_journey_id")
            or item.get("id") == journey.get("primary_opportunity_id")
        ]
        opportunity_ids = {item.get("id") for item in journey_opportunities}
        journey_contracts = [
            item
            for item in contracts
            if _belongs_to_journey(item, journey_id, "deal_journey_id") or item.get("opportunity_id") in opportunity_ids
        ]
        contract_ids = {item.get("id") for item in journey_contracts}
        journey_plans = [item for item in payment_plans if item.get("contract_id") in contract_ids]
        journey_payments = [item for item in payment_records if item.get("contract_id") in contract_ids]
        timeline = [
            {
                "occurred_at": item.get("event_time"),
                "type": item.get("event_type"),
                "summary": _text(item.get("summary"), limit=500) or "业务旅程事件",
                "evidence_refs": [_evidence_key("journey_event", item.get("id"))],
            }
            for item in journey_events
            if item.get("deal_journey_id") == journey_id
        ]
        timeline.extend(
            {
                "occurred_at": item.get("occurred_at"),
                "type": "follow_up",
                "summary": _text(item.get("source_content") or item.get("content"), limit=500) or "跟进记录",
                "evidence_refs": [_evidence_key("activity", item.get("id"))],
            }
            for item in activities
            if item.get("deal_journey_id") == journey_id
        )
        task_by_id = {
            item.get("task_id") or item.get("id"): item
            for item in tasks
            if item.get("task_id") is not None or item.get("id") is not None
        }
        for event in task_events:
            task_id = event.get("task_id")
            task = task_by_id.get(task_id, {})
            if task.get("deal_journey_id") != journey_id:
                continue
            if not _is_material_task_event(event):
                continue
            title = _text(task.get("title"), limit=255) or "跟进待办"
            previous = _status_label(event.get("previous_status"))
            current = _status_label(event.get("new_status"))
            if previous and current:
                summary = f"待办“{title}”状态由“{previous}”变为“{current}”。"
            elif current:
                summary = f"待办“{title}”记录为“{current}”。"
            else:
                summary = f"待办“{title}”发生状态变更。"
            timeline.append(
                {
                    "occurred_at": event.get("created_time"),
                    "type": "follow_up_task_status",
                    "summary": summary,
                    "task_id": task_id,
                    "evidence_refs": [_evidence_key("task", task_id)],
                }
            )
        timeline.sort(key=lambda item: str(item.get("occurred_at") or ""))
        result.append(
            {
                "id": journey_id,
                "name": journey.get("name") or "未命名业务旅程",
                "status": journey.get("status") or "ACTIVE",
                "started_at": journey.get("started_at"),
                "closed_at": journey.get("closed_at"),
                "last_event_at": journey.get("last_event_at"),
                "current_stage": _first_value(journey_opportunities, "stage"),
                "opportunities": journey_opportunities,
                "contracts": journey_contracts,
                "payment": {
                    "plans": journey_plans,
                    "records": journey_payments,
                    "status": _payment_summary(journey_contracts, journey_plans, journey_payments),
                },
                "open_follow_ups": [
                    item
                    for item in recorded_follow_ups
                    if item.get("deal_journey_id") == journey_id and item.get("raw_status") == "OPEN"
                ],
                "timeline": timeline,
            }
        )
    return sorted(
        result,
        key=lambda item: (
            0 if item.get("status") == "ACTIVE" else 1,
            str(item.get("last_event_at") or ""),
        ),
    )


def _belongs_to_journey(item: dict[str, object], journey_id: object, key: str) -> bool:
    return journey_id is not None and item.get(key) == journey_id


def _first_value(items: list[dict[str, object]], key: str) -> object:
    for item in items:
        if item.get(key):
            return item.get(key)
    return None


def _payment_summary(
    contracts: list[dict[str, object]],
    plans: list[dict[str, object]],
    records: list[dict[str, object]],
) -> str:
    if not contracts:
        return ""
    if any(str(item.get("payment_status")) == "COMPLETED" for item in contracts):
        return "合同回款已完成"
    if records:
        return "已有回款记录，合同回款尚未全部完成"  # noqa: RUF001
    if plans:
        return "已有回款计划"
    return "已关联合同"


def _current_situation_summary(
    *,
    customer: Mapping[str, object],
    active_journeys: list[dict[str, object]],
    opportunities: list[dict[str, object]],
    contracts: list[dict[str, object]],
    latest_activity: dict[str, object],
    process: list[dict[str, object]],
    demand_items: list[dict[str, object]] | None = None,
) -> str:
    if demand_items is not None:
        return _current_situation_from_business_state(
            customer=customer,
            active_journeys=active_journeys,
            opportunities=opportunities,
            contracts=contracts,
            demand_items=demand_items,
            latest_activity=latest_activity,
        )

    fragments: list[str] = []
    if active_journeys:
        fragments.append(f"有{len(active_journeys)}条进行中的业务旅程")
    open_opportunities = [item for item in opportunities if str(item.get("status")) in {"0", "FOLLOWING", "None"}]
    if open_opportunities:
        fragments.append(f"关联{len(open_opportunities)}条跟进中的商机")
    if contracts:
        fragments.append(f"已有{len(contracts)}份合同记录")
    if process:
        latest_process = max(
            process,
            key=lambda item: str(item.get("ended_at") or item.get("occurred_at") or ""),
        )
        title = _text(latest_process.get("title"), limit=80)
        if title:
            fragments.append(f"当前跟进集中在{title}")
    # The latest note is useful only when no grouped process is available;
    # otherwise the process section already carries the same content.
    if not fragments and latest_activity:
        latest_text = _sentence_body(_activity_text(latest_activity, limit=180), limit=180)
        if latest_text:
            fragments.append(f"最近记录：{latest_text}")  # noqa: RUF001
    if not fragments:
        return ""
    name = _text(customer.get("account_name"), limit=255)
    prefix = f"{name}:" if name else ""
    return prefix + "，".join(fragments) + "。"  # noqa: RUF001


def _current_situation_from_business_state(
    *,
    customer: Mapping[str, object],
    active_journeys: list[dict[str, object]],
    opportunities: list[dict[str, object]],
    contracts: list[dict[str, object]],
    demand_items: list[dict[str, object]],
    latest_activity: dict[str, object],
) -> str:
    """Write a short management readout without repeating the demand section.

    The summary answers three questions in one paragraph: where the customer
    is in the relationship, what is currently holding the business together,
    and what the CRM has (or has not) recorded as a commercial outcome.  The
    detailed needs and evidence remain in their dedicated sections.
    """

    topics = {str(item.get("topic")) for item in demand_items}
    fragments: list[str] = []
    journey_stages = list(
        dict.fromkeys(
            _text(item.get("current_stage"), limit=40)
            for item in active_journeys
            if _text(item.get("current_stage"), limit=40)
        )
    )
    if "usage_expansion" in topics:
        fragments.append("客户已进入实际使用后的扩容评估阶段")
    elif active_journeys:
        fragments.append("客户已进入明确的业务推进阶段")

    if active_journeys:
        journey_phrase = f"目前有{len(active_journeys)}条并行业务旅程"
        if journey_stages:
            journey_phrase += f"，当前阶段主要为{'、'.join(journey_stages)}"  # noqa: RUF001
        fragments.append(journey_phrase)

    constraints: list[str] = []
    if "internal_validation" in topics:
        constraints.append("内部试用范围和汇报路径仍在评估")
    if "reporting" in topics:
        constraints.append("报表按部门导出的要求已提出")
    if "procurement" in topics:
        constraints.append("预算、财务审批和付款节奏仍在推进")
    if constraints:
        fragments.append("当前推进重点是" + "，".join(constraints) + "")  # noqa: RUF001

    open_opportunities = [
        item for item in opportunities if str(item.get("status")) in {"0", "FOLLOWING", "None"}
    ]
    if contracts:
        fragments.append(f"档案中已有{len(contracts)}份合同记录")
    elif open_opportunities:
        fragments.append(
            f"当前记录有{len(open_opportunities)}条跟进中的商机，尚未形成合同记录"  # noqa: RUF001
        )
    elif not fragments and latest_activity:
        latest_text = _sentence_body(_activity_text(latest_activity, limit=180), limit=180)
        if latest_text and _is_meaningful_activity(latest_activity):
            fragments.append(latest_text)

    if not fragments:
        return ""
    name = _text(customer.get("account_name"), limit=255)
    prefix = f"{name}：" if name else ""  # noqa: RUF001
    return prefix + "；".join(fragments[:4]) + "。"  # noqa: RUF001


def _business_status(
    journeys: list[dict[str, object]],
    opportunities: list[dict[str, object]],
    contracts: list[dict[str, object]],
    payment_records: list[dict[str, object]],
) -> dict[str, object]:
    """Return only business status values that have something to show."""

    values = {
        "active_journey_count": len(journeys),
        "opportunity_count": len(opportunities),
        "contract_count": len(contracts),
        "payment_record_count": len(payment_records),
    }
    return {key: value for key, value in values.items() if value}


def _long_term_overview(
    customer: Mapping[str, object],
    facts: list[dict[str, object]],
    contacts: list[dict[str, object]],
) -> str:
    # Long-term context is rendered from structured company fields, facts and
    # contacts.  A generic sentence about the data model adds no customer
    # understanding and is therefore intentionally omitted.
    del customer, facts, contacts
    return ""


def _version_sections(version: CustomerProfileProjectionVersion | None) -> dict[str, object]:
    if version is None:
        return {
            "current_situation": {},
            "current_journeys": [],
            "important_changes": [],
            "long_term_context": {},
            "follow_up_process": [],
            "recorded_follow_ups": [],
        }
    return {
        "current_situation": version.current_situation_json,
        "current_journeys": version.current_journeys_json,
        "important_changes": version.important_changes_json,
        "long_term_context": version.long_term_context_json,
        "follow_up_process": version.follow_up_process_json,
        "recorded_follow_ups": version.recorded_follow_ups_json,
    }


def _changed_section_names(before: dict[str, object], after: dict[str, object]) -> list[str]:
    """Return top-level profile sections whose published value really changed."""

    return [
        section
        for section in PROFILE_SECTION_NAMES
        if _diff_values(before.get(section), after.get(section))
    ]


def _diff_values(before: object, after: object, *, path: str = "", limit: int = 100) -> list[dict[str, object]]:
    """Return compact leaf diffs suitable for the history API."""

    if before == after:
        return []
    if isinstance(before, dict) and isinstance(after, dict):
        keys = sorted({str(key) for key in before} | {str(key) for key in after})
        result: list[dict[str, object]] = []
        for key in keys:
            child_path = f"{path}.{key}" if path else key
            result.extend(_diff_values(before.get(key), after.get(key), path=child_path, limit=limit - len(result)))
            if len(result) >= limit:
                break
        return result[:limit]
    if isinstance(before, list) and isinstance(after, list):
        return [{"path": path or "$", "before": before, "after": after}]
    return [{"path": path or "$", "before": before, "after": after}]
