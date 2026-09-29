"""One closed-set action nomination against the assistant task snapshot."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.services.assistant.contracts import TaskDraft
from app.services.assistant.coordinator import NextActionDecision
from app.services.assistant.model_transport import AssistantLLMError, AssistantModelTransport, team_model_credentials

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.assistant import AssistantTask

# ruff: noqa: RUF001

ActionName = Literal["ask_field", "end"]


class ActionNomination(BaseModel):
    """Closed contract returned by the Agent LLM."""

    model_config = ConfigDict(extra="forbid")

    action: ActionName
    field: str | None = Field(default=None, max_length=64, description="ask_field 时必填：草稿槽位名")
    prompt: str | None = Field(default=None, max_length=500, description="ask_field 时向用户提的问题")
    reason: str | None = Field(default=None, max_length=200)


CHOOSER_SYSTEM_PROMPT = """你是 CRM 销售助手的动作选择器。根据任务当前状态，从封闭动作集中选择下一步。

可选动作：
- ask_field：草稿还缺关键信息，需要向用户追问一个字段。
  必须给出 field（只能是 customer/content/next_action/next_follow_time）和一句 prompt。
- end：任务目标已达成或无事可做。

规则：
- 只输出一个动作。不要规划多步。
- 已接受（ACCEPTED）的字段不要再追问。
- 活动已写入且后续提案已处理完时，选择 end。
- 不要发明字段名或动作名。输出必须符合结构化 schema。"""

_DRAFT_SLOT_LABELS = {
    "customer": "客户名称",
    "content": "跟进正文",
    "next_action": "下一步行动",
    "next_follow_time": "下次跟进时间",
}


class AgentLLMChooser:
    """Production chooser: one bounded structured call over the snapshot."""

    def __init__(self, runtime: object | None = None) -> None:
        self.runtime = runtime or AssistantModelTransport()

    def _snapshot_prompt(self, task: AssistantTask) -> str:
        draft = TaskDraft.model_validate(task.draft_json or {})
        slots = []
        for name, label in _DRAFT_SLOT_LABELS.items():
            slot = getattr(draft, name)
            state = slot.status
            value = (slot.value or "")[:80]
            slots.append(f"- {name}（{label}）：{state}" + (f"「{value}」" if value else ""))
        committed = [str(item.get("kind", "")) for item in task.committed_json or []]
        from app.services.assistant.task_state import load_waiting

        waiting = load_waiting(task)
        waiting_line = f"当前等待：{waiting.type}/{waiting.field}" if waiting else "当前等待：无"
        return (
            f"任务目标：{task.goal}\n"
            f"活动类型：{task.activity_kind or '未定'}\n"
            f"{waiting_line}\n"
            "草稿字段：\n" + "\n".join(slots) + "\n"
            f"已提交结果：{committed or '无'}\n"
            "请选择下一个动作。"
        )

    async def choose(self, task: AssistantTask) -> NextActionDecision:
        db: Session | None = getattr(task, "_sa_instance_state", None) and task._sa_instance_state.session
        if db is None:
            raise AssistantLLMError("任务未关联数据库会话")

        host, key, name = team_model_credentials(db, task.team_id)
        try:
            result = await self.runtime.ainvoke_structured(
                api_host=host,
                api_key=key,
                model=name,
                temperature=0.0,
                system_prompt=CHOOSER_SYSTEM_PROMPT,
                user_prompt=self._snapshot_prompt(task),
                response_model=ActionNomination,
                error_prefix="动作选择",
            )
            if result is None:
                raise AssistantLLMError("动作选择：结构化输出不可用")
            result = ActionNomination.model_validate(result)
        except AssistantLLMError:
            raise
        except (RuntimeError, ValueError, TypeError) as exc:
            raise AssistantLLMError("动作选择：结构化输出无效") from exc

        parameters: dict[str, object] = {"reason": result.reason or ""}
        if result.action == "ask_field":
            if result.field not in _DRAFT_SLOT_LABELS or not result.prompt or not result.prompt.strip():
                raise AssistantLLMError("动作选择：追问字段或内容无效")
            parameters["field"] = result.field
            parameters["prompt"] = result.prompt
        return NextActionDecision(action=result.action, parameters=parameters)
