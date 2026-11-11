"""Read-only follow-up evidence and server-owned change judgment.

The intelligence context and vector index stay on their legacy source policy.
This pack is a separate, permission-filtered read for one follow-up confirmation.
"""

# ruff: noqa: RUF001

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Literal

from pydantic import ValidationError

from app.services.assistant.action_evidence import SourceSegment, parse_deadline
from app.services.assistant.contracts import ComparisonCurrentSource, ComparisonHistoricalSource, FollowUpComparison

from app.services.assistant.llm import AssistantLLM, AssistantLLMError
from app.services.assistant.llm_contracts import ChangeJudgment
from app.services.assistant.temporal_evidence import PROTOCOL_VERSION, StoredAction, StoredMention

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.customer import Customer
    from app.models.opportunity import Opportunity

SectionStatus = Literal["ready", "empty", "denied", "failed"]
ChoiceKind = Literal["bound", "ask", "none", "unavailable", "stale"]

AUTO_CONFIDENCE = 0.85
AUTO_MARGIN = 0.25
ACTIVITY_LIMIT = 5
ACTIVITY_WINDOW_DAYS = 90
SUMMARY_LIMIT = 80
NOTICE_NO_ACTIVITY = "暂无近期已确认跟进"
NOTICE_NO_OPPORTUNITY = "没有进行中商机"
NOTICE_DENIED = "没有权限查看这部分内容"
NOTICE_FAILED = "这部分暂时没有读到"
NOTICE_STALE = "数据可能已过期"
OPPORTUNITY_PROMPT = "请选择这次沟通对应的商机。"

CONTEXT_COMMAND_KEYS = (
    "comparison",
    "context_status",
    "change_signal",
    "change_summary",
    "opportunity_name",
    "opportunity_stage",
    "context_as_of",
    "context_notices",
    "context_evidence",
)


@dataclass(frozen=True)
class EvidenceItem:
    ref: str
    source_type: str
    occurred_at: str | None
    summary: str


@dataclass(frozen=True)
class OpportunityOption:
    index: int
    public_id: str
    name: str
    stage: str | None


@dataclass
class EvidencePack:
    activities_status: SectionStatus = "empty"
    opportunities_status: SectionStatus = "empty"
    tasks_status: SectionStatus = "empty"
    commitments_status: SectionStatus = "empty"
    activities: list[EvidenceItem] = field(default_factory=list)
    tasks: list[EvidenceItem] = field(default_factory=list)
    commitments: list[EvidenceItem] = field(default_factory=list)
    opportunities: list[OpportunityOption] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)
    as_of: str | None = None

    def known_refs(self) -> set[str]:
        return {
            item.ref
            for status, items in ((self.activities_status, self.activities), (self.tasks_status, self.tasks),
                                  (self.commitments_status, self.commitments))
            if status == "ready" for item in items
        }

    def model_items(self) -> list[dict[str, str | None]]:
        return [
            {
                "ref": item.ref,
                "source_type": item.source_type,
                "occurred_at": item.occurred_at,
                "summary": item.summary,
            }
            for status, items in ((self.activities_status, self.activities), (self.tasks_status, self.tasks),
                                  (self.commitments_status, self.commitments))
            if status == "ready" for item in items
        ]


@dataclass(frozen=True)
class OpportunityChoice:
    kind: ChoiceKind
    public_id: str | None = None
    name: str | None = None
    stage: str | None = None
    candidates: tuple[dict[str, str], ...] = ()
    notices: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChangeCard:
    comparison: FollowUpComparison | None
    context_status: str | None
    opportunity_name: str | None
    opportunity_stage: str | None
    context_as_of: str | None
    context_notices: tuple[str, ...]
    context_evidence: tuple[dict[str, object], ...]

    def as_command(self) -> dict[str, object]:
        return {
            "comparison": self.comparison.model_dump(mode="json") if self.comparison is not None else None,
            "context_status": self.context_status,
            "opportunity_name": self.opportunity_name,
            "opportunity_stage": self.opportunity_stage,
            "context_as_of": self.context_as_of,
            "context_notices": list(self.context_notices),
            "context_evidence": [dict(item) for item in self.context_evidence],
        }


def _clip(text: str) -> str:
    compact = " ".join(text.split())
    if len(compact) <= SUMMARY_LIMIT:
        return compact
    return compact[: SUMMARY_LIMIT - 1] + "…"


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def name_hits(options: list[OpportunityOption], user_text: str) -> list[OpportunityOption]:
    return [item for item in options if len(item.name.strip()) >= 2 and item.name in user_text]


def select_opportunity(
    options: list[OpportunityOption],
    user_text: str,
    ranking: list[tuple[int, float]] | None,
    *,
    rank_failed: bool,
) -> OpportunityChoice:
    """Bind one visible opportunity, or ask. Never invent an id."""

    if not options:
        return OpportunityChoice("none", notices=(NOTICE_NO_OPPORTUNITY,))
    hits = name_hits(options, user_text)
    if len(hits) == 1:
        chosen = hits[0]
        return OpportunityChoice("bound", chosen.public_id, chosen.name, chosen.stage)
    if len(hits) > 1 or len(options) == 1:
        if len(options) == 1 and len(hits) != 1:
            only = options[0]
            return OpportunityChoice("bound", only.public_id, only.name, only.stage)
        return _ask(options)
    if rank_failed or not ranking:
        return _ask(options)
    seen: set[int] = set()
    clean: list[tuple[int, float]] = []
    for index, confidence in sorted(ranking, key=lambda item: item[1], reverse=True):
        if index in seen or index < 0 or index >= len(options) or not 0 <= confidence <= 1:
            return _ask(options)
        seen.add(index)
        clean.append((index, confidence))
    if not clean:
        return _ask(options)
    top_index, top_confidence = clean[0]
    second = clean[1][1] if len(clean) > 1 else 0.0
    if top_confidence >= AUTO_CONFIDENCE and top_confidence - second >= AUTO_MARGIN:
        chosen = options[top_index]
        return OpportunityChoice("bound", chosen.public_id, chosen.name, chosen.stage)
    return _ask(options)


def _ask(options: list[OpportunityOption]) -> OpportunityChoice:
    candidates = tuple(
        {"id": item.public_id, "label": f"{item.name} · {item.stage}" if item.stage else item.name}
        for item in options
    )
    return OpportunityChoice("ask", candidates=candidates)


def _quote_matches(text: str, start: int, end: int, quote: str) -> bool:
    return 0 <= start < end <= len(text) and text[start:end] == quote


def _matter_clause(text: str, subject: str, *, quoted: str) -> str | None:
    """A quote must include the one complete source clause naming this matter."""

    clauses = [match.group().strip() for match in re.finditer(r"[^，,。；;！？!?\n]+", text) if subject in match.group()]
    if len(clauses) != 1 or clauses[0].count(subject) != 1 or clauses[0] not in quoted:
        return None
    return clauses[0]


def _matter_predicate(clause: str, subject: str, predicate: str) -> bool:
    # Do not borrow a predicate/date from an unpunctuated second matter either.
    suffix = clause.split(subject, 1)[1].strip()
    return re.match(r"(?:的)?(?:时间|日期|计划)?" + predicate, suffix) is not None


def verify_comparison(
    judged: ChangeJudgment,
    *,
    pack: EvidencePack,
    source_records: list[SourceSegment],
    content_json: dict[str, object],
) -> FollowUpComparison | None:
    """Validate both source authorities before allowing one concrete, nonduplicated difference."""

    candidate = judged.candidate
    if candidate is None or judged.classification not in {"CUSTOMER_COMMITMENT", "RESCHEDULE"}:
        return None
    expected_increment = "DATE_CHANGED" if judged.classification == "RESCHEDULE" else "NEW_CUSTOMER_CONFIRMATION"
    if candidate.increment != expected_increment:
        return None
    current, previous = candidate.current, candidate.previous
    records = {item.segment_id: item for item in source_records}
    record = records.get(current.segment_id)
    if record is None or not _quote_matches(record.text, current.quote_start, current.quote_end, current.quote):
        return None
    if len(records) != len(source_records):
        return None
    sections = (
        (pack.activities_status, pack.activities), (pack.tasks_status, pack.tasks),
        (pack.commitments_status, pack.commitments),
    )
    history = next((item for status, items in sections if status == "ready" for item in items if item.ref == previous.ref), None)
    if history is None or not _quote_matches(history.summary, previous.quote_start, previous.quote_end, previous.quote):
        return None
    # Historical summaries are a separate authority, never another copy of current speech.
    if any(previous.quote in item.text for item in source_records):
        return None
    bundle = content_json.get("temporal_evidence")
    if not isinstance(bundle, dict) or bundle.get("version") != PROTOCOL_VERSION:
        return None
    try:
        actions = [StoredAction.model_validate(item) for item in bundle.get("actions", [])]
        mentions = [StoredMention.model_validate(item) for item in bundle.get("mentions", [])]
    except (ValidationError, TypeError):
        return None
    matching = [item for item in actions if item.action_id == candidate.action_id and item.state == "ACTIVE"]
    if len(matching) != 1:
        return None
    action = matching[0]
    if action.owner_role != "CUSTOMER" or action.action_status != "COMMITTED":
        return None
    if action.source_segment_id != current.segment_id:
        return None
    if not _quote_matches(record.text, action.quote_start, action.quote_end, action.evidence_quote):
        return None
    if not (current.quote_start <= action.quote_start < action.quote_end <= current.quote_end):
        return None
    linked = [item for item in mentions if item.action_id == action.action_id and item.state == "ACTIVE"]
    if any(item.role != "CUSTOMER_COMMITMENT" for item in linked):
        return None
    if action.temporal_mention_id is not None and not any(item.mention_id == action.temporal_mention_id for item in linked):
        return None
    # The same literal matter must be present in both sources and the already accepted action.
    subject = candidate.subject.strip()
    if len(subject) < 2 or any(subject not in text for text in (action.action_text, current.quote, previous.quote)):
        return None
    historical_clause = _matter_clause(history.summary, subject, quoted=previous.quote)
    if historical_clause is None:
        return None
    previous_date = current_date = None
    if judged.classification == "RESCHEDULE":
        if not candidate.previous_date or not candidate.current_date or not history.occurred_at:
            return None
        if not _matter_predicate(
            historical_clause, subject,
            r"(?:原定|定于|安排在|安排为|原为|为|是|在|于|已确认|确认|定在)?\s*" + re.escape(candidate.previous_date),
        ):
            return None
        current_clause = _matter_clause(action.evidence_quote, subject, quoted=current.quote)
        if current_clause is None or not _matter_predicate(
            current_clause, subject,
            r"(?:现|现已|已)?(?:改至|改到|改为|延期至|延期到|推迟至|推迟到|延后至|延后到)\s*" + re.escape(candidate.current_date),
        ):
            return None
        active_dates = [
            item for item in mentions
            if item.mention_id == action.temporal_mention_id and item.action_id == action.action_id
            and item.state == "ACTIVE" and item.role == "CUSTOMER_COMMITMENT"
            and item.resolution_status == "RESOLVED" and item.resolved_at is not None
        ]
        if len(active_dates) != 1:
            return None
        mention = active_dates[0]
        if mention.source_segment_id != record.segment_id or mention.raw_text != candidate.current_date:
            return None
        if not _quote_matches(record.text, mention.quote_start, mention.quote_end, mention.raw_text):
            return None
        if not (action.quote_start <= mention.quote_start < mention.quote_end <= action.quote_end):
            return None
        try:
            old_at, old_granularity = parse_deadline(candidate.previous_date, anchor=datetime.fromisoformat(history.occurred_at))
            new_at, new_granularity = parse_deadline(candidate.current_date, anchor=record.recorded_at)
        except (ValueError, TypeError):
            return None
        if old_at is None or new_at is None or old_granularity not in {"DATE", "DATETIME"} or new_granularity not in {"DATE", "DATETIME"}:
            return None
        if old_granularity != new_granularity or new_at != mention.resolved_at or new_at <= old_at:
            return None
        if new_granularity == "DATETIME":
            precision = "seconds" if old_at.second or new_at.second else "minutes"
            previous_date = old_at.isoformat(sep=" ", timespec=precision)
            current_date = new_at.isoformat(sep=" ", timespec=precision)
        else:
            previous_date, current_date = old_at.date().isoformat(), new_at.date().isoformat()
        summary = f"{subject}由 {previous_date} 改至 {current_date}。"
    else:
        # An already recorded commitment is not a new confirmation. With no explicit
        # historical absence of an arrangement, prefer omitting a speculative increment.
        if not _matter_predicate(
            historical_clause, subject,
            r"(?:仍|还|目前|此前)?(?:尚未|未定|待定|未明确|未确认|待确认|待确定|没有明确)",
        ):
            return None
        summary = f"此前记录：{historical_clause}；本次已明确，具体承诺见上方。"
    return FollowUpComparison(
        kind=judged.classification, subject=subject, action_id=action.action_id, summary=summary,
        current=ComparisonCurrentSource(**current.model_dump()),
        previous=ComparisonHistoricalSource(**previous.model_dump(), source_type=history.source_type, occurred_at=history.occurred_at),
        previous_date=previous_date, current_date=current_date,
    )


def render_change_card(
    pack: EvidencePack,
    choice: OpportunityChoice,
    *,
    comparison: FollowUpComparison | None,
    status: str | None,
) -> ChangeCard:
    evidence = [
        {"source_type": item.source_type, "occurred_at": item.occurred_at, "summary": item.summary,
         "relation": "背景", "key": False}
        for section, items in ((pack.activities_status, pack.activities), (pack.tasks_status, pack.tasks),
                               (pack.commitments_status, pack.commitments))
        if section == "ready" for item in items
        if comparison is None or item.ref != comparison.previous.ref
    ]
    show_opportunity = choice.kind == "bound"
    return ChangeCard(
        comparison=comparison, context_status=status,
        opportunity_name=choice.name if show_opportunity else None,
        opportunity_stage=choice.stage if show_opportunity else None,
        context_as_of=pack.as_of,
        context_notices=tuple(_dedupe([*pack.notices, *choice.notices])),
        context_evidence=tuple(evidence),
    )


def _permission_codes(db: Session, user_id: int, team_id: int) -> set[str]:
    from app.crud.permission import permission_crud

    return {permission.code for permission in permission_crud.get_user_permissions(db, user_id, team_id)}


def can_view_customer(
    db: Session, *, team_id: int, user_id: int, customer: Customer, permission_codes: set[str]
) -> bool:
    from app.crud.customer_member import customer_member_crud

    if "customer:view:all" in permission_codes:
        return True
    if customer_member_crud.has_access(db, team_id, int(customer.id), str(user_id), "VIEW"):
        return True
    return "customer:view:own" in permission_codes and customer.owner_id == str(user_id)


def load_visible_opportunity(
    db: Session,
    *,
    team_id: int,
    user_id: int,
    customer_id: int,
    public_id: str,
    permission_codes: set[str],
) -> Opportunity | None:
    from app.models.opportunity import Opportunity

    row = (
        db.query(Opportunity)
        .filter(
            Opportunity.team_id == team_id,
            Opportunity.customer_id == customer_id,
            Opportunity.public_id == public_id,
            Opportunity.status == 0,
        )
        .one_or_none()
    )
    if row is None:
        return None
    if "opportunity:view:all" in permission_codes:
        return row
    if "opportunity:view:own" in permission_codes and row.owner_id == str(user_id):
        return row
    return None


def _failed_section(pack: EvidencePack, name: str) -> None:
    setattr(pack, f"{name}_status", "failed")
    pack.notices.append(NOTICE_FAILED)


def read_follow_up_evidence(
    db: Session,
    *,
    team_id: int,
    user_id: int,
    customer: Customer,
    permission_codes: set[str] | None = None,
) -> EvidencePack:
    """One fresh read. Failures stay on their own section and never reuse a cache."""

    from app.models.customer_activity import CustomerActivity
    from app.models.opportunity import Opportunity
    from app.models.sales_commitment import FollowUpTask, SalesCommitment
    from app.services.customer_activity_kinds import get_activity_kind_meta
    from app.utils.time import business_now

    codes = set(permission_codes) if permission_codes is not None else _permission_codes(db, user_id, team_id)
    pack = EvidencePack()
    now = business_now()
    readable = True
    try:
        if not can_view_customer(db, team_id=team_id, user_id=user_id, customer=customer, permission_codes=codes):
            pack.activities_status = "denied"
            pack.notices.append(NOTICE_DENIED)
            readable = False
        else:
            cutoff = now - timedelta(days=ACTIVITY_WINDOW_DAYS)
            rows = (
                db.query(CustomerActivity)
                .filter(
                    CustomerActivity.team_id == team_id,
                    CustomerActivity.customer_id == customer.id,
                    CustomerActivity.processing_status == "COMPLETED",
                    CustomerActivity.occurred_at >= cutoff,
                )
                .order_by(CustomerActivity.occurred_at.desc(), CustomerActivity.id.desc())
                .limit(ACTIVITY_LIMIT)
                .all()
            )
            pack.activities = [
                EvidenceItem(
                    ref=f"A{index}",
                    source_type=str(get_activity_kind_meta(row.activity_kind)["label"]),
                    occurred_at=row.occurred_at.strftime("%Y-%m-%d %H:%M") if row.occurred_at else None,
                    summary=_clip(row.summary or row.source_content or ""),
                )
                for index, row in enumerate(rows, start=1)
                if _clip(row.summary or row.source_content or "")
            ]
            pack.activities_status = "ready" if pack.activities else "empty"
            if pack.activities_status == "empty":
                pack.notices.append(NOTICE_NO_ACTIVITY)
    except Exception:
        logger.exception("follow-up activity evidence failed")
        _failed_section(pack, "activities")
        readable = False

    try:
        if "opportunity:view:all" not in codes and "opportunity:view:own" not in codes:
            pack.opportunities_status = "denied"
            pack.notices.append(NOTICE_DENIED)
        else:
            query = db.query(Opportunity).filter(
                Opportunity.team_id == team_id,
                Opportunity.customer_id == customer.id,
                Opportunity.status == 0,
            )
            if "opportunity:view:all" not in codes:
                query = query.filter(Opportunity.owner_id == str(user_id))
            rows = query.order_by(Opportunity.id.asc()).all()
            pack.opportunities = [
                OpportunityOption(
                    index=index,
                    public_id=row.public_id,
                    name=row.opportunity_name,
                    stage=row.current_stage_name,
                )
                for index, row in enumerate(rows)
            ]
            pack.opportunities_status = "ready" if pack.opportunities else "empty"
            if pack.opportunities_status == "empty":
                pack.notices.append(NOTICE_NO_OPPORTUNITY)
    except Exception:
        logger.exception("follow-up opportunity evidence failed")
        _failed_section(pack, "opportunities")

    view_all_tasks = bool(codes.intersection({"follow_up_task:view:all", "follow_up_task:view:team"}))
    try:
        query = db.query(FollowUpTask).filter(
            FollowUpTask.team_id == team_id,
            FollowUpTask.customer_id == customer.id,
            FollowUpTask.status == "OPEN",
        )
        if not view_all_tasks:
            query = query.filter(FollowUpTask.owner_id == str(user_id))
        rows = query.order_by(FollowUpTask.due_at.asc(), FollowUpTask.id.asc()).all()
        pack.tasks = [
            EvidenceItem(
                ref=f"T{index}",
                source_type="任务",
                occurred_at=row.due_at.strftime("%Y-%m-%d %H:%M") if row.due_at else None,
                summary=_clip(row.title),
            )
            for index, row in enumerate(rows, start=1)
        ]
        pack.tasks_status = "ready" if pack.tasks else "empty"
    except Exception:
        logger.exception("follow-up task evidence failed")
        _failed_section(pack, "tasks")

    try:
        query = db.query(SalesCommitment).filter(
            SalesCommitment.team_id == team_id,
            SalesCommitment.customer_id == customer.id,
            SalesCommitment.status == "OPEN",
        )
        if not view_all_tasks:
            query = query.filter(SalesCommitment.owner_id == str(user_id))
        rows = query.order_by(SalesCommitment.id.asc()).all()
        pack.commitments = [
            EvidenceItem(
                ref=f"C{index}",
                source_type="承诺",
                occurred_at=row.due_at.strftime("%Y-%m-%d %H:%M") if row.due_at else None,
                summary=_clip(row.title),
            )
            for index, row in enumerate(rows, start=1)
        ]
        pack.commitments_status = "ready" if pack.commitments else "empty"
    except Exception:
        logger.exception("follow-up commitment evidence failed")
        _failed_section(pack, "commitments")

    if readable or pack.opportunities_status in {"ready", "empty", "denied"}:
        pack.as_of = now.strftime("%Y-%m-%d %H:%M")
    pack.notices = _dedupe(pack.notices)
    return pack


class RealFollowUpContext:
    """Production adapter. Models nominate; this object applies the server rules."""

    def __init__(self, llm: AssistantLLM | None = None) -> None:
        self.llm = llm or AssistantLLM()

    async def locate_customer(self, db: Session, *, team_id: int, user_text: str) -> str:
        found = await self.llm.locate_customer(db, team_id=team_id, user_text=user_text)
        return found.customer_name.strip()

    def read_evidence(self, db: Session, *, team_id: int, user_id: int, customer: Customer) -> EvidencePack:
        try:
            return read_follow_up_evidence(db, team_id=team_id, user_id=user_id, customer=customer)
        except Exception:
            logger.exception("follow-up evidence pack failed")
            pack = EvidencePack(
                activities_status="failed",
                opportunities_status="failed",
                tasks_status="failed",
                commitments_status="failed",
                notices=[NOTICE_FAILED],
            )
            return pack

    async def choose_opportunity(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        customer: Customer,
        user_text: str,
        pack: EvidencePack,
        bound_public_id: str | None,
        bound_stage: str | None,
    ) -> OpportunityChoice:
        if pack.opportunities_status == "failed":
            return OpportunityChoice("unavailable", notices=(NOTICE_FAILED,))
        if pack.opportunities_status == "denied":
            return OpportunityChoice("unavailable", notices=(NOTICE_DENIED,))
        if pack.opportunities_status != "ready":
            return OpportunityChoice("none", notices=(NOTICE_NO_OPPORTUNITY,))
        codes = _permission_codes(db, user_id, team_id)
        if bound_public_id:
            row = load_visible_opportunity(
                db,
                team_id=team_id,
                user_id=user_id,
                customer_id=int(customer.id),
                public_id=bound_public_id,
                permission_codes=codes,
            )
            if row is not None:
                stage = row.current_stage_name
                if bound_stage is not None and (stage or "") != bound_stage:
                    return OpportunityChoice("stale", notices=(NOTICE_STALE,))
                return OpportunityChoice("bound", row.public_id, row.opportunity_name, stage)
        ranking: list[tuple[int, float]] | None = None
        rank_failed = False
        if len(pack.opportunities) > 1 and not name_hits(pack.opportunities, user_text):
            try:
                ranked = await self.llm.rank_opportunities(
                    db,
                    team_id=team_id,
                    user_text=user_text,
                    candidates=[
                        {"index": item.index, "name": item.name, "stage": item.stage} for item in pack.opportunities
                    ],
                )
                ranking = [(item.index, item.confidence) for item in ranked.ranked]
            except AssistantLLMError:
                rank_failed = True
        choice = select_opportunity(pack.opportunities, user_text, ranking, rank_failed=rank_failed)
        if choice.kind != "bound" or choice.public_id is None:
            return choice
        confirmed = load_visible_opportunity(
            db,
            team_id=team_id,
            user_id=user_id,
            customer_id=int(customer.id),
            public_id=choice.public_id,
            permission_codes=codes,
        )
        if confirmed is None:
            return _ask(pack.opportunities)
        return OpportunityChoice("bound", confirmed.public_id, confirmed.opportunity_name, confirmed.current_stage_name)

    async def judge(
        self,
        db: Session,
        *,
        team_id: int,
        pack: EvidencePack,
        choice: OpportunityChoice,
        source_records: list[SourceSegment | dict[str, object]],
        content_json: dict[str, object],
    ) -> ChangeCard:
        comparison = None
        status = "未形成可验证的历史对比，仍可确认本次活动。"
        try:
            records = [SourceSegment.model_validate(item) for item in source_records]
        except (ValidationError, TypeError):
            records = []
        if choice.kind not in {"unavailable", "stale"} and records and pack.known_refs():
            try:
                judged = await self.llm.judge_change(
                    db, team_id=team_id,
                    source_records=[item.model_dump(mode="json") for item in records],
                    action_evidence=content_json.get("temporal_evidence"),
                    evidence=pack.model_items(),
                    opportunity_name=choice.name if choice.kind == "bound" else None,
                    opportunity_stage=choice.stage if choice.kind == "bound" else None,
                )
                comparison = verify_comparison(judged, pack=pack, source_records=records, content_json=content_json)
                if comparison is not None:
                    status = None
                elif judged.classification == "SALES_ACTION":
                    status = "本次是销售行动，不作为客户新增承诺。"
                elif judged.classification == "NO_CHANGE":
                    status = "未发现可单独展示的历史差异。"
            except (AssistantLLMError, ValidationError, TypeError, ValueError):
                status = "历史对比暂时不可用，仍可确认本次活动。"
        elif not pack.known_refs():
            status = "暂无可用于比较的授权历史，本次活动仍可确认。"
        return render_change_card(pack, choice, comparison=comparison, status=status)
