"""Bounded model nomination of purchase and stage signals from a committed activity."""

from __future__ import annotations

# ruff: noqa: RUF001 -- Chinese user-facing copy uses native punctuation.
import json
from operator import attrgetter
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.services.assistant.failure_contract import attempt_budget_remaining
from app.services.assistant.model_transport import (
    AssistantLLMError,
    AssistantModelTransport,
    team_model_credentials,
    team_output_mode,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.assistant import AssistantTask
    from app.models.customer_activity import CustomerActivity
    from app.services.assistant.crm_proposal_commands import ProposalData


class PurchaseSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["opportunity_create"]
    evidence_quote: str = Field(min_length=1, max_length=500)
    segment_id: str = Field(min_length=1, max_length=64)


class StageAdvanceSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    opportunity_ref: str = Field(min_length=1, max_length=64)
    advance: Literal[True]
    quote: str = Field(min_length=1, max_length=500)

    @model_validator(mode="before")
    @classmethod
    def retain_signal_fields(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        if value.get("advance") is not True:
            raise ValueError("stage nomination requires advance: true")
        # Keep the advertised schema closed and discard any model-supplied IDs or other extra fields.
        return {key: value[key] for key in ("opportunity_ref", "advance", "quote") if key in value}


class OpportunityNominations(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates: list[PurchaseSignal | StageAdvanceSignal] = Field(max_length=10)


_SYSTEM_PROMPT = """你是销售助手的商机信号提名器，不是 CRM 操作员。
从已提交的最终活动及仍有效的原话中，只提名明确采购或明确推进某条现有商机阶段的信号。
无有效信号返回 {"candidates": []}。不得引用被明确更正或撤销的旧事实，不得猜测客户、目标、阶段或商业字段。
创建只输出 kind=opportunity_create、原话连续引文 evidence_quote 和所在原话段的 segment_id；不输出金额等表单字段。
仅当原话明确表示把 active_opportunities 中某条商机推进到所列的 next_stage_name 时\uFF0C才输出
{"opportunity_ref":"A1","advance":true,"quote":"原话中的精确连续引文"}；引文必须含下一阶段名称\uFF0C不输出任何 CRM ID。
你不能签发任务动作、确认、命令 ID 或宣称已写入。输出必须符合结构化 schema。"""


def _stage_options(
    db: Session, task: AssistantTask, customer_id: int
) -> tuple[list[dict[str, str | None]], dict[str, tuple[str, int | None, int, int, str]]]:
    from app.models.opportunity import Opportunity, OpportunityStatus
    from app.services.assistant.crm_proposal_commands import adjacent_stage

    active = (
        db.query(Opportunity)
        .filter(
            Opportunity.team_id == task.team_id,
            Opportunity.customer_id == customer_id,
            Opportunity.status == OpportunityStatus.FOLLOWING.value,
        )
        .order_by(Opportunity.id)
        .all()
    )
    options: list[dict[str, str | None]] = []
    bindings: dict[str, tuple[str, int | None, int, int, str]] = {}
    for row in active:
        transition = adjacent_stage(db, task, row)
        if transition is None:
            continue
        snapshot, stage = transition
        ref = f"A{len(options) + 1}"
        # Read scalar instance values from the legacy Column-based models.
        public_id: str = attrgetter("public_id")(row)
        snapshot_id: int | None = attrgetter("current_stage_snapshot_id")(row)
        version: int = attrgetter("version")(row)
        stage_id: int = attrgetter("id")(stage)
        stage_name: str = attrgetter("stage_name")(stage)
        bindings[ref] = (public_id, snapshot_id, version, stage_id, stage_name)
        options.append(
            {
                "opportunity_ref": ref,
                "name": attrgetter("opportunity_name")(row),
                "current_stage_name": attrgetter("stage_name")(snapshot) if snapshot is not None else None,
                "next_stage_name": stage_name,
            }
        )
    return options, bindings


class OpportunityNominator:
    """Model suggests signals; the server separately binds evidence and CRM authority."""

    def __init__(self, runtime: AssistantModelTransport | None = None) -> None:
        self.runtime = runtime or AssistantModelTransport()

    async def nominate(self, db: Session, task: AssistantTask, activity: CustomerActivity) -> list[ProposalData]:
        content_json: str | None = attrgetter("content_json")(activity)
        try:
            content = json.loads(content_json or "{}")
        except (TypeError, ValueError) as exc:
            raise AssistantLLMError("商机提名：活动内容无效") from exc
        if not isinstance(content, dict):
            raise AssistantLLMError("商机提名：活动内容无效")

        records = content.get("source_records")
        segments = [
            {"segment_id": str(record.get("segment_id") or ""), "text": str(record.get("text") or "")}
            for record in (records if isinstance(records, list) else [])
            if isinstance(record, dict) and record.get("segment_id") and record.get("text")
        ]
        if not segments:
            source_content: str = attrgetter("source_content")(activity)
            segments = [{"segment_id": "seg_primary", "text": source_content or ""}]
        segments = [item for item in segments if item["text"]]

        customer_id: int | None = attrgetter("customer_id")(activity)
        opportunities, bindings = (
            _stage_options(db, task, customer_id)
            if activity.team_id == task.team_id and customer_id is not None
            else ([], {})
        )
        source_revision = activity.activity_revision

        host, key, name = team_model_credentials(db, task.team_id)
        try:
            result = await self.runtime.ainvoke_structured(
                api_host=host,
                api_key=key,
                model=name,
                output_mode=team_output_mode(db, task.team_id),
                temperature=0.0,
                system_prompt=_SYSTEM_PROMPT,
                user_prompt=json.dumps(
                    {
                        "activity_revision": source_revision,
                        "canonical": content,
                        "source_segments": segments,
                        "active_opportunities": opportunities,
                    },
                    ensure_ascii=False,
                ),
                response_model=OpportunityNominations,
                error_prefix="商机提名",
                timeout_seconds=attempt_budget_remaining(),
                stage="nominate",
            )
            if result is None:
                raise AssistantLLMError("商机提名：结构化输出不可用")
            nominations = OpportunityNominations.model_validate(result)
        except AssistantLLMError:
            raise
        except (RuntimeError, ValueError, TypeError) as exc:
            raise AssistantLLMError("商机提名：结构化输出无效") from exc

        candidates: list[ProposalData] = []
        for item in nominations.candidates:
            if isinstance(item, PurchaseSignal):
                candidates.append({**item.model_dump(), "payload": {}})
                continue
            binding = bindings.get(item.opportunity_ref)
            if binding is None:
                continue
            public_id, snapshot_id, version, stage_id, stage_name = binding
            candidates.append(
                {
                    "kind": "opportunity_stage",
                    "target_public_id": public_id,
                    "evidence_quote": item.quote,
                    "payload": {},
                    "_nominated_transition": (source_revision, snapshot_id, version, stage_id, stage_name),
                }
            )
        return candidates


opportunity_nominator = OpportunityNominator()
