"""Bounded model nomination of purchase and stage signals from a committed activity."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.services.assistant.model_transport import AssistantLLMError, AssistantModelTransport, team_model_credentials

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.assistant import AssistantTask
    from app.models.customer_activity import CustomerActivity


class OpportunitySignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["opportunity_create", "opportunity_stage"]
    evidence_quote: str = Field(min_length=1, max_length=500)
    segment_id: str = Field(min_length=1, max_length=64)
    target_public_id: str | None = None
    stage_template_id: int | None = None


class OpportunityNominations(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates: list[OpportunitySignal] = Field(max_length=10)


_SYSTEM_PROMPT = """你是销售助手的商机信号提名器，不是 CRM 操作员。
从已提交的最终活动及仍有效的原话中，只提名明确采购或明确推进某条现有商机阶段的信号。
无有效信号返回 {"candidates": []}。逐条引用原话中精确连续的 evidence_quote 和所在完整原话段的 segment_id；
不得引用被明确更正或撤销的旧事实，不得猜测客户、目标、阶段或商业字段。
创建只输出 kind=opportunity_create、evidence_quote、segment_id；不输出金额等表单字段。
阶段推进还须给出已列出现有商机的 target_public_id 和相邻 stage_template_id。
你不能签发任务动作、确认、命令 ID 或宣称已写入。输出必须符合结构化 schema。"""


class OpportunityNominator:
    """Model suggests signals; the server separately binds evidence and CRM authority."""

    def __init__(self, runtime: AssistantModelTransport | None = None) -> None:
        self.runtime = runtime or AssistantModelTransport()

    async def nominate(self, db: Session, task: AssistantTask, activity: CustomerActivity) -> list[dict]:
        from app.models.opportunity import Opportunity
        from app.models.procurement import OpportunityStageSnapshot
        from app.services.assistant.task_state import load_draft

        try:
            content = json.loads(activity.content_json or "{}")
        except (TypeError, ValueError) as exc:
            raise AssistantLLMError("商机提名：活动内容无效") from exc
        if not isinstance(content, dict):
            raise AssistantLLMError("商机提名：活动内容无效")

        draft: TaskDraft = load_draft(task)
        records = content.get("source_records") if isinstance(content.get("source_records"), list) else []
        segments = [
            {"segment_id": str(record.get("segment_id") or ""), "text": str(record.get("text") or "")}
            for record in records
            if isinstance(record, dict) and record.get("segment_id") and record.get("text")
        ]
        if not segments:
            segments = [{"segment_id": "seg_primary", "text": activity.source_content or ""}]
        segments = [item for item in segments if item["text"]]

        active = (
            db.query(Opportunity)
            .filter(
                Opportunity.team_id == task.team_id,
                Opportunity.customer_id == activity.customer_id,
                Opportunity.status == 0,
            )
            .all()
        )
        opportunities = []
        for row in active:
            snapshot = (
                db.query(OpportunityStageSnapshot)
                .filter(
                    OpportunityStageSnapshot.team_id == task.team_id,
                    OpportunityStageSnapshot.id == row.current_stage_snapshot_id,
                )
                .one_or_none()
                if row.current_stage_snapshot_id
                else None
            )
            opportunities.append(
                {
                    "public_id": row.public_id,
                    "name": row.opportunity_name,
                    "current_stage": snapshot.stage_name if snapshot else None,
                }
            )

        host, key, name = team_model_credentials(db, task.team_id)
        try:
            result = await self.runtime.ainvoke_structured(
                api_host=host,
                api_key=key,
                model=name,
                temperature=0.0,
                system_prompt=_SYSTEM_PROMPT,
                user_prompt=json.dumps(
                    {
                        "activity_revision": activity.activity_revision,
                        "canonical": content,
                        "source_segments": segments,
                        "active_opportunities": opportunities,
                    },
                    ensure_ascii=False,
                ),
                response_model=OpportunityNominations,
                error_prefix="商机提名",
            )
            if result is None:
                raise AssistantLLMError("商机提名：结构化输出不可用")
            nominations = OpportunityNominations.model_validate(result)
        except AssistantLLMError:
            raise
        except (RuntimeError, ValueError, TypeError) as exc:
            raise AssistantLLMError("商机提名：结构化输出无效") from exc

        return [
            {
                "kind": item.kind,
                "evidence_quote": item.evidence_quote,
                "segment_id": item.segment_id,
                **(
                    {"target_public_id": item.target_public_id, "payload": {"stage_template_id": item.stage_template_id}}
                    if item.kind == "opportunity_stage"
                    else {"payload": {}}
                ),
            }
            for item in nominations.candidates
            if item.kind != "opportunity_stage" or (item.target_public_id and item.stage_template_id)
        ]


opportunity_nominator = OpportunityNominator()
