"""Read-only follow-up evidence and server-owned change judgment.

The intelligence context and vector index stay on their legacy source policy.
This pack is a separate, permission-filtered read for one follow-up confirmation.
"""

# ruff: noqa: RUF001

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import TYPE_CHECKING, Literal

from app.services.assistant.llm import AssistantLLM, AssistantLLMError

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.customer import Customer
    from app.models.opportunity import Opportunity

SectionStatus = Literal["ready", "empty", "denied", "failed"]
Signal = Literal["推进", "持平", "放缓", "待确认"]
ChoiceKind = Literal["bound", "ask", "none", "unavailable", "stale"]

AUTO_CONFIDENCE = 0.85
AUTO_MARGIN = 0.25
ACTIVITY_LIMIT = 5
ACTIVITY_WINDOW_DAYS = 90
SUMMARY_LIMIT = 80
HESITATION_PHRASES = ("再考虑", "考虑一下", "再看看")

SIGNAL_SUMMARY: dict[str, str] = {
    "推进": "这次出现了新的确认或下一步。",
    "持平": "这次和近期记录相比，没有足够的新变化。",
    "放缓": "这次出现了等待或延期，还不是丢单。",
    "待确认": "现有依据不够，先不判断变化。",
}
CONFLICT_SUMMARY = "来源有冲突，先不判断变化。"
NOTICE_NO_ACTIVITY = "暂无近期已确认跟进"
NOTICE_NO_OPPORTUNITY = "没有进行中商机"
NOTICE_DENIED = "没有权限查看这部分内容"
NOTICE_FAILED = "这部分暂时没有读到"
NOTICE_STALE = "数据可能已过期"
OPPORTUNITY_PROMPT = "请选择这次沟通对应的商机。"

CONTEXT_COMMAND_KEYS = (
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
        return {item.ref for item in (*self.activities, *self.tasks, *self.commitments)}

    def model_items(self) -> list[dict[str, str | None]]:
        return [
            {
                "ref": item.ref,
                "source_type": item.source_type,
                "occurred_at": item.occurred_at,
                "summary": item.summary,
            }
            for item in (*self.activities, *self.tasks, *self.commitments)
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
    change_signal: str
    change_summary: str
    opportunity_name: str | None
    opportunity_stage: str | None
    context_as_of: str | None
    context_notices: tuple[str, ...]
    context_evidence: tuple[dict[str, object], ...]

    def as_command(self) -> dict[str, object]:
        return {
            "change_signal": self.change_signal,
            "change_summary": self.change_summary,
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


def decide_signal(
    *,
    proposed: str,
    uses: list[tuple[str, str]],
    known_refs: set[str],
    user_text: str,
) -> tuple[str, str]:
    """Canonical sentence only. 放缓 requires an in-window citation, so 再考虑 alone cannot become 放缓."""

    valid = [(ref, relation) for ref, relation in uses if ref in known_refs]
    relations = {relation for _, relation in valid}
    if "冲突" in relations or {"推进", "放缓"} <= relations:
        return "待确认", CONFLICT_SUMMARY
    signal = proposed if proposed in SIGNAL_SUMMARY else "待确认"
    cited_slowdown = any(relation == "放缓" for _, relation in valid)
    hesitation = any(phrase in user_text for phrase in HESITATION_PHRASES)
    if signal == "放缓" and (not cited_slowdown or (hesitation and not cited_slowdown)):
        signal = "待确认"
    return signal, SIGNAL_SUMMARY[signal]


def render_change_card(
    pack: EvidencePack,
    choice: OpportunityChoice,
    *,
    signal: str,
    summary: str,
    uses: list[tuple[str, str]],
) -> ChangeCard:
    relations = {ref: relation for ref, relation in uses if ref in pack.known_refs()}
    cited = [item for item in (*pack.activities, *pack.tasks, *pack.commitments) if item.ref in relations]
    highlights = cited[:2]
    if not highlights and pack.activities:
        highlights = pack.activities[:1]
    highlight_refs = {item.ref for item in highlights}
    evidence = [
        {
            "source_type": item.source_type,
            "occurred_at": item.occurred_at,
            "summary": item.summary,
            "relation": relations.get(item.ref, "背景"),
            "key": item.ref in highlight_refs,
        }
        for item in (*pack.activities, *pack.tasks, *pack.commitments)
    ]
    show_opportunity = choice.kind == "bound"
    notices = _dedupe([*pack.notices, *choice.notices])
    if signal == "待确认" and summary == CONFLICT_SUMMARY and CONFLICT_SUMMARY not in notices:
        notices = _dedupe([CONFLICT_SUMMARY, *notices])
    return ChangeCard(
        change_signal=signal,
        change_summary=summary,
        opportunity_name=choice.name if show_opportunity else None,
        opportunity_stage=choice.stage if show_opportunity else None,
        context_as_of=pack.as_of,
        context_notices=tuple(notices),
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
        user_text: str,
        pack: EvidencePack,
        choice: OpportunityChoice,
    ) -> ChangeCard:
        uses: list[tuple[str, str]] = []
        proposed = "待确认"
        if choice.kind not in {"unavailable", "stale"}:
            try:
                judged = await self.llm.judge_change(
                    db,
                    team_id=team_id,
                    user_text=user_text,
                    evidence=pack.model_items(),
                    opportunity_name=choice.name if choice.kind == "bound" else None,
                    opportunity_stage=choice.stage if choice.kind == "bound" else None,
                )
                proposed = judged.signal
                uses = [(item.ref, item.relation) for item in judged.uses]
            except AssistantLLMError:
                proposed = "待确认"
        signal, summary = decide_signal(
            proposed=proposed, uses=uses, known_refs=pack.known_refs(), user_text=user_text
        )
        if choice.kind in {"unavailable", "stale"}:
            signal, summary = "待确认", SIGNAL_SUMMARY["待确认"]
        return render_change_card(pack, choice, signal=signal, summary=summary, uses=uses)
