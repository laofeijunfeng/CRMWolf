# 确认写入生命周期 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 所有 `CONFIRMATION_REQUIRED` 写入共用同一套运行时：确认前闭世界枚举、确认卡只读 facts、不可重试失败退役确认卡并报告已成功原子、下一轮禁止重放已成功 create。

**Architecture:** Planner 在出确认卡前做确定性枚举映射；Workflow 确认交互增加只读 `facts`，不改 `confirm/cancel`。Effect 失败携带 `committed_resources`；application 对不可重试 FAILED complete 确认 action，可重试仍 release。Planner 对团队内精确同名唯一线索/客户改绑剩余 command。前端锁跟 ledger 走。

**Tech Stack:** FastAPI, Pydantic, LangGraph Workflow, Vue 3, Zod, pytest, Vitest.

**Spec:** `docs/superpowers/specs/2026-09-16-confirmed-write-lifecycle-design.md`

## Global Constraints

- 一次发布必须同时具备四条契约。缺一不算完成。任务按依赖拆，但不得单独合入半成品。
- 不把多 command 包进一个 DB 事务，不做补偿 saga。
- 确认 WAITING 仍只接受结构化按钮。纯文本不得 resume 确认卡。
- 不给线索首次跟上客户活动质量评分 / 下一步门禁。
- 不把 `lead` 加进 `CRMResource` / Query catalog。
- 不在 Root 用正则识别「电话」。
- 不在确认卡上开可编辑 `fields`。
- 不改 ADR 0001 / 0002 正文。
- 不改无关脏工作区文件。
- 前端禁止 `: any`、`as any`、`@ts-ignore`、无必要 `!`。
- 中间任务只跑本任务写明的聚焦测试，不跑全量 lint / type-check / 全量 pytest。
- 错误文案必须逐字匹配本计划里的字符串。

## 文件结构与职责

- Create: `CRM-Server/app/services/agent/workflow/write_enums.py` — 线索跟进方式、公司规模闭世界映射。
- Create: `CRM-Server/tests/unit/test_agent_write_enums.py` — 映射表测试。
- Modify: `CRM-Server/app/services/agent/workflow/planning.py` — `_plan_lead` / `_plan_customer` 用映射；非法 method 出五选一；确认 facts；同名唯一对象改绑。
- Modify: `CRM-Server/app/services/agent/prompts.py` — lead `follow_up_method` 枚举与 API 对齐。
- Modify: `CRM-Server/app/services/agent/tool_registry.py` — `CreateLeadFollowUpInput.method: FollowUpMethod`。
- Modify: `CRM-Server/app/services/agent/workflow/contracts.py` — `WorkflowConfirmationFact`、`WorkflowCommittedResource`、失败结果字段。
- Modify: `CRM-Server/app/services/agent/workflow/execution.py` — 记录已提交资源；不可重试失败改写用户文案。
- Modify: `CRM-Server/app/services/agent/workflow/graph.py` — FAILED 结果带 committed / failed_command_id。
- Modify: `CRM-Server/app/services/agent/application.py` — 不可重试 FAILED complete 确认 action。
- Modify: `CRM-Server/app/services/agent/ui/schemas.py` / `composer.py` — 确认 facts 投影。
- Modify: `CRM-Client/src/schemas/agent-contracts/ui-interactions.ts` — Zod 同步 `facts`。
- Modify: `CRM-Client/src/components/agent-ui/AgentUIInteractionBlock.vue` — 只读渲染 facts。
- Modify: `CRM-Client/src/components/agent/CRMAgentChat.vue` — `submitInteraction` 结束后解锁。
- Modify: `CONTEXT.md`、`CRM-Docs/design-agent/runtime/hitl-guardrails.md`、`CRM-Docs/design-agent/runtime/interaction-policy.md`。

---

### Task 1: Closed-world write enums

**Files:**
- Create: `CRM-Server/app/services/agent/workflow/write_enums.py`
- Create: `CRM-Server/tests/unit/test_agent_write_enums.py`

**Interfaces:**
- Consumes: `app.models.lead.FollowUpMethod`, `app.models.lead.CompanyScale`.
- Produces: `UnmappedLeadFollowUpMethod(raw: str)`；`canonicalize_lead_follow_up_method(value: object) -> FollowUpMethod`；`canonicalize_company_scale(value: object) -> str | None`（返回中文枚举值，如 `"1-50人"`）。

- [ ] **Step 1: Write the failing tests**

Create `CRM-Server/tests/unit/test_agent_write_enums.py`:

```python
import pytest

from app.models.lead import FollowUpMethod
from app.services.agent.workflow.write_enums import (
    UnmappedLeadFollowUpMethod,
    canonicalize_company_scale,
    canonicalize_lead_follow_up_method,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, FollowUpMethod.OTHER),
        ("", FollowUpMethod.OTHER),
        ("  ", FollowUpMethod.OTHER),
        ("电话", FollowUpMethod.PHONE),
        ("PHONE", FollowUpMethod.PHONE),
        ("phone", FollowUpMethod.PHONE),
        ("电话联系", FollowUpMethod.PHONE),
        ("电话沟通", FollowUpMethod.PHONE),
        ("来电", FollowUpMethod.PHONE),
        ("微信", FollowUpMethod.WECHAT),
        ("WECHAT", FollowUpMethod.WECHAT),
        ("wechat", FollowUpMethod.WECHAT),
        ("拜访", FollowUpMethod.VISIT),
        ("VISIT", FollowUpMethod.VISIT),
        ("邮件", FollowUpMethod.EMAIL),
        ("EMAIL", FollowUpMethod.EMAIL),
        ("email", FollowUpMethod.EMAIL),
        ("其他", FollowUpMethod.OTHER),
        ("OTHER", FollowUpMethod.OTHER),
        ("other", FollowUpMethod.OTHER),
        ("会议", FollowUpMethod.OTHER),
        ("线上会议", FollowUpMethod.OTHER),
        ("线下会议", FollowUpMethod.OTHER),
        ("视频会议", FollowUpMethod.OTHER),
    ],
)
def test_canonicalize_lead_follow_up_method(raw, expected):
    assert canonicalize_lead_follow_up_method(raw) is expected


def test_unmapped_lead_follow_up_method_raises():
    with pytest.raises(UnmappedLeadFollowUpMethod) as exc:
        canonicalize_lead_follow_up_method("传真")
    assert exc.value.raw == "传真"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None),
        ("", None),
        ("10~29", "1-50人"),
        ("10-29", "1-50人"),
        ("15人左右", "1-50人"),
        ("1-50人", "1-50人"),
        ("51-200人", "51-200人"),
        ("SCALE_1_50", "1-50人"),
        ("无法识别的规模", None),
    ],
)
def test_canonicalize_company_scale(raw, expected):
    assert canonicalize_company_scale(raw) == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd CRM-Server && pytest tests/unit/test_agent_write_enums.py -q`

Expected: FAIL with `ModuleNotFoundError: write_enums`

- [ ] **Step 3: Write minimal implementation**

Create `CRM-Server/app/services/agent/workflow/write_enums.py`:

```python
"""Deterministic write-side enum canonicalization for Workflow planning."""

from __future__ import annotations

import re

from app.models.lead import CompanyScale, FollowUpMethod

_LEAD_FOLLOW_UP_METHOD_ALIASES: dict[str, FollowUpMethod] = {
    "电话": FollowUpMethod.PHONE,
    "phone": FollowUpMethod.PHONE,
    "电话联系": FollowUpMethod.PHONE,
    "电话沟通": FollowUpMethod.PHONE,
    "来电": FollowUpMethod.PHONE,
    "微信": FollowUpMethod.WECHAT,
    "wechat": FollowUpMethod.WECHAT,
    "拜访": FollowUpMethod.VISIT,
    "visit": FollowUpMethod.VISIT,
    "邮件": FollowUpMethod.EMAIL,
    "email": FollowUpMethod.EMAIL,
    "其他": FollowUpMethod.OTHER,
    "other": FollowUpMethod.OTHER,
    "会议": FollowUpMethod.OTHER,
    "线上会议": FollowUpMethod.OTHER,
    "线下会议": FollowUpMethod.OTHER,
    "视频会议": FollowUpMethod.OTHER,
}

_COMPANY_SCALE_BY_TEXT: dict[str, str] = {
    member.value: member.value for member in CompanyScale
}
_COMPANY_SCALE_BY_TEXT.update({member.name: member.value for member in CompanyScale})
_COMPANY_SCALE_BY_TEXT.update(
    {
        "10~29": CompanyScale.SCALE_1_50.value,
        "10-29": CompanyScale.SCALE_1_50.value,
        "15人左右": CompanyScale.SCALE_1_50.value,
        "15人": CompanyScale.SCALE_1_50.value,
    }
)


class UnmappedLeadFollowUpMethod(ValueError):
    def __init__(self, raw: str) -> None:
        self.raw = raw
        super().__init__(raw)


def canonicalize_lead_follow_up_method(value: object) -> FollowUpMethod:
    if value is None:
        return FollowUpMethod.OTHER
    if isinstance(value, FollowUpMethod):
        return value
    if not isinstance(value, str):
        raise UnmappedLeadFollowUpMethod(str(value))
    stripped = value.strip()
    if not stripped:
        return FollowUpMethod.OTHER
    if stripped in FollowUpMethod._value2member_map_:
        return FollowUpMethod(stripped)
    alias = _LEAD_FOLLOW_UP_METHOD_ALIASES.get(stripped) or _LEAD_FOLLOW_UP_METHOD_ALIASES.get(
        stripped.casefold()
    )
    if alias is not None:
        return alias
    raise UnmappedLeadFollowUpMethod(stripped)


def canonicalize_company_scale(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, CompanyScale):
        return value.value
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped:
        return None
    direct = _COMPANY_SCALE_BY_TEXT.get(stripped) or _COMPANY_SCALE_BY_TEXT.get(stripped.casefold())
    if direct is not None:
        return direct
    match = re.fullmatch(r"(\d+)\s*人(?:左右)?", stripped)
    if match is not None:
        count = int(match.group(1))
        if 1 <= count <= 50:
            return CompanyScale.SCALE_1_50.value
        if 51 <= count <= 200:
            return CompanyScale.SCALE_51_200.value
        if 201 <= count <= 500:
            return CompanyScale.SCALE_201_500.value
        if 501 <= count <= 1000:
            return CompanyScale.SCALE_501_1000.value
        if count > 1000:
            return CompanyScale.SCALE_1000_PLUS.value
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd CRM-Server && pytest tests/unit/test_agent_write_enums.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/app/services/agent/workflow/write_enums.py CRM-Server/tests/unit/test_agent_write_enums.py
git commit -m "feat(agent): canonicalize lead follow-up method enums"
```

---

### Task 2: Planner, prompt, and tool consume enums

**Files:**
- Modify: `CRM-Server/tests/unit/test_agent_lead_customer_product_fields.py`
- Modify: `CRM-Server/app/services/agent/workflow/planning.py`
- Modify: `CRM-Server/app/services/agent/prompts.py`
- Modify: `CRM-Server/app/services/agent/tool_registry.py`

**Interfaces:**
- Consumes: `canonicalize_lead_follow_up_method`, `canonicalize_company_scale`, `UnmappedLeadFollowUpMethod`, `FollowUpMethod`.
- Produces: `_plan_lead` 在确认前把 `method` 写成 `FollowUpMethod` 中文值；非法 method 抛 `WorkflowPlanningNeedsInput`，`interaction_type="choice"`，`business_action="select_lead_follow_up_method"`；`_semantic_for_request` 把该 choice 的 `content` 写回 `lead.follow_up_method`；`CreateLeadFollowUpInput.method: FollowUpMethod = FollowUpMethod.OTHER`。

- [ ] **Step 1: Write the failing planner tests**

Append to `CRM-Server/tests/unit/test_agent_lead_customer_product_fields.py`:

```python
from app.models.lead import FollowUpMethod


def test_plan_lead_defaults_blank_follow_up_method_to_other():
    plan = _plan_lead(
        SimpleNamespace(**_lead_kwargs(product_public_id="prd_1"), follow_up_content="已电话沟通"),
        db=object(),
    )
    assert plan.commands[1].payload["method"] == FollowUpMethod.OTHER.value


def test_plan_lead_maps_online_meeting_method_to_other():
    plan = _plan_lead(
        SimpleNamespace(
            **_lead_kwargs(product_public_id="prd_1"),
            follow_up_content="开了线上会议",
            follow_up_method="线上会议",
        ),
        db=object(),
    )
    assert plan.commands[1].payload["method"] == FollowUpMethod.OTHER.value


def test_plan_lead_unmapped_method_asks_for_closed_choice():
    with pytest.raises(WorkflowPlanningNeedsInput) as exc:
        _plan_lead(
            SimpleNamespace(
                **_lead_kwargs(product_public_id="prd_1"),
                follow_up_content="发了传真",
                follow_up_method="传真",
            ),
            db=object(),
        )
    interaction = exc.value.interaction
    assert interaction.interaction_type == "choice"
    assert interaction.business_action == "select_lead_follow_up_method"
    assert [option.value for option in interaction.options] == ["电话", "微信", "拜访", "邮件", "其他"]


def test_plan_lead_maps_tilde_scale_to_one_to_fifty():
    plan = _plan_lead(
        SimpleNamespace(**_lead_kwargs(product_public_id="prd_1", company_scale="10~29")),
        db=object(),
    )
    assert plan.commands[0].payload["lead"]["company_scale"] == "1-50人"


def test_create_lead_follow_up_input_rejects_unmapped_method():
    from app.services.agent.tool_registry import CreateLeadFollowUpInput

    with pytest.raises(ValidationError):
        CreateLeadFollowUpInput(lead_id="lead_001", content="跟进", method="线上会议")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd CRM-Server && pytest tests/unit/test_agent_lead_customer_product_fields.py::test_plan_lead_defaults_blank_follow_up_method_to_other tests/unit/test_agent_lead_customer_product_fields.py::test_plan_lead_maps_online_meeting_method_to_other tests/unit/test_agent_lead_customer_product_fields.py::test_plan_lead_unmapped_method_asks_for_closed_choice tests/unit/test_agent_lead_customer_product_fields.py::test_plan_lead_maps_tilde_scale_to_one_to_fifty tests/unit/test_agent_lead_customer_product_fields.py::test_create_lead_follow_up_input_rejects_unmapped_method -q`

Expected: FAIL — blank method currently becomes `"其他"` only when follow-up exists, but `"线上会议"` is passed through; `"传真"` does not raise; `"10~29"` is copied verbatim; tool input accepts any str.

- [ ] **Step 3: Implement planner, prompt, and tool schema**

In `CRM-Server/app/services/agent/prompts.py` change the lead `follow_up_method` line to:

```python
    "follow_up_method": "电话|微信|拜访|邮件|其他|null",
```

In `CRM-Server/app/services/agent/tool_registry.py`:

```python
from app.models.lead import FollowUpMethod
```

Change `CreateLeadFollowUpInput` to:

```python
class CreateLeadFollowUpInput(BaseModel):
    lead_id: LeadIdentifier = Field(..., description="线索对外ID；兼容历史任务中的数据库ID")
    content: str = Field(..., min_length=1)
    method: FollowUpMethod = FollowUpMethod.OTHER
    next_action: Optional[str] = None
    next_follow_time: AgentDatetimeText = None
    idempotency_suffix: Optional[str] = None
```

In `planning.py` imports add:

```python
from app.models.lead import FollowUpMethod
from app.services.agent.workflow.write_enums import (
    UnmappedLeadFollowUpMethod,
    canonicalize_company_scale,
    canonicalize_lead_follow_up_method,
)
```

Inside `_plan_lead`, after building `lead` and before `missing_fields`:

```python
        scale = canonicalize_company_scale(lead.get("company_scale"))
        if scale is None:
            lead.pop("company_scale", None)
        else:
            lead["company_scale"] = scale
```

Replace the follow-up method assignment. After `follow_up_content` is known to be a non-empty string, before building `follow_up_payload`:

```python
        try:
            method = canonicalize_lead_follow_up_method(
                getattr(lead_model, "follow_up_method", None)
            )
        except UnmappedLeadFollowUpMethod:
            raise WorkflowPlanningNeedsInput(
                WorkflowInteraction(
                    interaction_id=f"int_{workflow_id.removeprefix('wf_')}_lead_follow_up_method",
                    interaction_type="choice",
                    business_action="select_lead_follow_up_method",
                    title="选择跟进方式",
                    prompt="请选择线索跟进方式。",
                    options=[
                        WorkflowInteractionOption(
                            value=item.value,
                            label=item.value,
                            metadata={"follow_up_method": item.value},
                        )
                        for item in FollowUpMethod
                    ],
                    selection_mode="single",
                    min_selections=1,
                    max_selections=1,
                    submit_label="继续",
                )
            )
        follow_up_payload: dict[str, object] = {
            "content": follow_up_content.strip(),
            "method": method.value,
        }
```

Delete the old `"method": getattr(lead_model, "follow_up_method", None) or "其他"` line.

In `_semantic_for_request`, inside the supplement loop, add:

```python
            elif business_action == "select_lead_follow_up_method":
                if semantic.lead is not None:
                    semantic.lead = semantic.lead.model_copy(
                        update={"follow_up_method": supplement.content}
                    )
```

Also canonicalize `company_scale` in `_plan_customer` the same way after building `flat_customer` (optional field, omit when unmapped). Do not run lead follow-up method mapping on customer activity.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd CRM-Server && pytest tests/unit/test_agent_write_enums.py tests/unit/test_agent_lead_customer_product_fields.py tests/unit/test_agent_workflow_subgraph.py::test_create_lead_with_follow_up_confirms_once_and_binds_created_lead_id -q`

Expected: PASS. Existing subgraph test still sends `method: "电话"`.

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/app/services/agent/workflow/planning.py CRM-Server/app/services/agent/prompts.py CRM-Server/app/services/agent/tool_registry.py CRM-Server/tests/unit/test_agent_lead_customer_product_fields.py
git commit -m "feat(agent): reject unmapped lead follow-up methods before confirm"
```

---

### Task 3: Read-only confirmation facts

**Files:**
- Modify: `CRM-Server/app/services/agent/workflow/contracts.py`
- Modify: `CRM-Server/app/services/agent/workflow/__init__.py`
- Modify: `CRM-Server/app/services/agent/workflow/planning.py`
- Modify: `CRM-Server/app/services/agent/ui/schemas.py`
- Modify: `CRM-Server/app/services/agent/ui/composer.py`
- Modify: `CRM-Client/src/schemas/agent-contracts/ui-interactions.ts`
- Modify: `CRM-Client/src/components/agent-ui/AgentUIInteractionBlock.vue`
- Modify: `CRM-Client/src/components/agent-ui/__tests__/AgentUIInteractionBlock.test.ts`
- Modify: `CRM-Server/tests/unit/test_agent_lead_customer_product_fields.py`
- Modify: `CRM-Server/tests/unit/test_agent_workflow_subgraph.py`

**Interfaces:**
- Consumes: Task 2 canonical method/scale values.
- Produces: `WorkflowConfirmationFact(key: str, label: str, value: str)`；`WorkflowInteraction.facts: list[WorkflowConfirmationFact] = []`（仅 confirmation 允许非空）；`InteractionBlock.facts` 同形；`_confirmation_commands_plan(..., facts: list[WorkflowConfirmationFact] | None = None)`。

- [ ] **Step 1: Write failing contract and UI tests**

Add to `test_agent_lead_customer_product_fields.py`:

```python
def test_plan_lead_with_follow_up_projects_confirmation_facts():
    plan = _plan_lead(
        SimpleNamespace(
            **_lead_kwargs(product_public_id="prd_1", company_scale="10~29"),
            follow_up_content="已确认需要安排产品演示",
            follow_up_method="电话",
            next_action="安排产品演示",
        ),
        db=object(),
    )
    assert plan.interaction is not None
    facts = {fact.key: fact.value for fact in plan.interaction.facts}
    assert facts["lead_name"] == "A"
    assert facts["follow_up_method"] == "电话"
    assert facts["follow_up_content"] == "已确认需要安排产品演示"
    assert facts["company_scale"] == "1-50人"
    assert facts["next_action"] == "安排产品演示"
```

In `test_agent_workflow_subgraph.py::test_create_lead_with_follow_up_confirms_once_and_binds_created_lead_id`, after asserting `business_action`, add:

```python
    fact_map = {fact.key: fact.value for fact in waiting.workflow_result.interaction.facts}
    assert fact_map["follow_up_method"] == "电话"
    assert fact_map["lead_name"] == "上海云图科技"
```

In `CRM-Client/src/components/agent-ui/__tests__/AgentUIInteractionBlock.test.ts` add:

```typescript
it('renders confirmation facts above confirm and cancel', () => {
  const block = InteractionBlockSchema.parse({
    id: 'b_lead_confirmation_facts',
    type: 'interaction',
    interaction_id: 'int_lead_confirmation_facts',
    interaction_type: 'confirmation',
    selection_mode: 'single',
    submit_on_select: true,
    state: 'ACTIVE',
    prompt: '确认要创建线索“协鑫数智科技”并记录首次跟进吗?',
    fields: [],
    facts: [
      { key: 'lead_name', label: '线索名称', value: '协鑫数智科技' },
      { key: 'follow_up_method', label: '跟进方式', value: '其他' },
    ],
    options: [
      { value: 'confirm', label: '确认创建', description: null, disabled: false },
      { value: 'cancel', label: '取消', description: null, disabled: false },
    ],
    submit_label: '确认',
    submit_action_id: 'act_lead_confirmation_facts',
  })

  const wrapper = mount(AgentUIInteractionBlock, { props: { block } })
  const facts = wrapper.get('[data-agent-ui-confirmation-facts]')
  expect(facts.text()).toContain('线索名称')
  expect(facts.text()).toContain('协鑫数智科技')
  expect(facts.text()).toContain('跟进方式')
  expect(facts.text()).toContain('其他')
  expect(wrapper.findAll('button')).toHaveLength(2)
})
```

Existing confirmation fixtures omit `facts`; schema default must be `[]` so they still parse.

- [ ] **Step 2: Run tests to verify they fail**

Run:

```text
cd CRM-Server && pytest tests/unit/test_agent_lead_customer_product_fields.py::test_plan_lead_with_follow_up_projects_confirmation_facts tests/unit/test_agent_workflow_subgraph.py::test_create_lead_with_follow_up_confirms_once_and_binds_created_lead_id -q
cd CRM-Client && npm run test:unit -- src/components/agent-ui/__tests__/AgentUIInteractionBlock.test.ts
```

Expected: FAIL — `WorkflowInteraction` has no `facts`; Zod rejects unknown `facts`.

- [ ] **Step 3: Implement facts across contracts, planner, composer, and UI**

In `contracts.py`, before `WorkflowInteraction`, add:

```python
class WorkflowConfirmationFact(WorkflowContractModel):
    key: str = Field(min_length=1, max_length=128, pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1, max_length=200)
    value: str = Field(min_length=1, max_length=10_000)
```

Add to `WorkflowInteraction`:

```python
    facts: list[WorkflowConfirmationFact] = Field(default_factory=list, max_length=20)
```

In `validate_shape`, after the form/fields checks, add:

```python
        if self.facts and self.interaction_type != "confirmation":
            raise ValueError("facts are only valid for confirmation interactions")
```

Export `WorkflowConfirmationFact` from `workflow/__init__.py`.

In `planning.py` import `WorkflowConfirmationFact`. Change `_confirmation_commands_plan` and `_confirmation_plan` to accept `facts: list[WorkflowConfirmationFact] | None = None` and pass `facts=facts or []` into `WorkflowInteraction`.

Add helper on `CRMWorkflowPlanner`:

```python
    @staticmethod
    def _confirmation_facts(items: list[tuple[str, str, object]]) -> list[WorkflowConfirmationFact]:
        facts: list[WorkflowConfirmationFact] = []
        for key, label, raw in items:
            if raw is None:
                continue
            value = raw if isinstance(raw, str) else str(raw)
            stripped = value.strip()
            if stripped:
                facts.append(WorkflowConfirmationFact(key=key, label=label, value=stripped))
        return facts
```

In `_plan_lead` follow-up confirmation, pass:

```python
            facts=self._confirmation_facts(
                [
                    ("lead_name", "线索名称", lead_name),
                    ("contact_name", "联系人", lead.get("contact_name")),
                    ("contact_phone", "联系电话", lead.get("contact_phone")),
                    ("city", "城市", lead.get("city")),
                    ("company_scale", "团队规模", lead.get("company_scale")),
                    ("product", "产品", lead.get("product_public_id")),
                    ("follow_up_method", "跟进方式", method.value),
                    ("follow_up_content", "跟进内容", follow_up_content.strip()),
                    ("next_action", "下一步", follow_up_payload.get("next_action")),
                ]
            ),
```

Lead-only confirmation (no follow-up) should still project lead identity facts without follow-up keys.

In `_plan_customer` combined confirmation, pass customer name, activity content, `activity_kind`, next_action.

In `ui/schemas.py` add `InteractionConfirmationFact` matching the three fields, and `facts: list[InteractionConfirmationFact] = Field(default_factory=list, max_length=20)` on `InteractionBlock`. Confirmation branch must still forbid `fields`, and must not forbid `facts`.

In `composer.py` `_interaction_block`, map:

```python
        facts = [
            InteractionConfirmationFact(key=fact.key, label=fact.label, value=fact.value)
            for fact in interaction.facts
        ]
```

Pass `facts=facts` into `InteractionBlock`.

In `CRM-Client/src/schemas/agent-contracts/ui-interactions.ts`:

```typescript
export const InteractionConfirmationFactSchema = z.object({
  key: z.string().min(1).max(128).regex(/^[a-z][a-z0-9_]*$/),
  label: z.string().min(1).max(200),
  value: z.string().min(1).max(10000)
}).strict()
```

Add `facts: z.array(InteractionConfirmationFactSchema).max(20).default([])` to `InteractionBlockObjectSchema`. In `validateInteractionBlock`, if `facts.length > 0` and type is not `confirmation`, add an issue.

In `AgentUIInteractionBlock.vue`, after the header and before the submitted-choice / options block, insert:

```vue
    <dl
      v-if="block.facts.length > 0"
      class="grid gap-2 rounded-lg border border-border/70 bg-background/70 px-3 py-2 text-sm"
      data-agent-ui-confirmation-facts
    >
      <div v-for="fact in block.facts" :key="fact.key" class="grid gap-0.5">
        <dt class="text-xs text-muted-foreground">{{ fact.label }}</dt>
        <dd class="m-0 whitespace-pre-wrap text-foreground">{{ fact.value }}</dd>
      </div>
    </dl>
```

TypeScript: `block.facts` comes from parsed schema default `[]`.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```text
cd CRM-Server && pytest tests/unit/test_agent_lead_customer_product_fields.py tests/unit/test_agent_workflow_subgraph.py::test_create_lead_with_follow_up_confirms_once_and_binds_created_lead_id tests/unit/test_agent_workflow_subgraph.py::test_create_customer_with_activity_confirms_once_and_binds_created_customer_id -q
cd CRM-Client && npm run test:unit -- src/components/agent-ui/__tests__/AgentUIInteractionBlock.test.ts src/schemas/agent-contracts
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/app/services/agent/workflow/contracts.py CRM-Server/app/services/agent/workflow/__init__.py CRM-Server/app/services/agent/workflow/planning.py CRM-Server/app/services/agent/ui/schemas.py CRM-Server/app/services/agent/ui/composer.py CRM-Server/tests/unit/test_agent_lead_customer_product_fields.py CRM-Server/tests/unit/test_agent_workflow_subgraph.py CRM-Client/src/schemas/agent-contracts/ui-interactions.ts CRM-Client/src/components/agent-ui/AgentUIInteractionBlock.vue CRM-Client/src/components/agent-ui/__tests__/AgentUIInteractionBlock.test.ts
git commit -m "feat(agent): project confirmation facts onto write cards"
```

---

### Task 4: Committed resources on effect failure

**Files:**
- Modify: `CRM-Server/app/services/agent/workflow/contracts.py`
- Modify: `CRM-Server/app/services/agent/workflow/execution.py`
- Modify: `CRM-Server/app/services/agent/workflow/graph.py`
- Modify: `CRM-Server/tests/unit/test_agent_workflow_subgraph.py`

**Interfaces:**
- Consumes: `AgentToolResult.data` dict with `id` / `public_id` / `lead_name` / `account_name`.
- Produces: `WorkflowCommittedResource(command_id, tool_name, resource, public_id, display_name)`；`WorkflowEffectResult.committed_resources` / `failed_command_id`；`WorkflowFailedResult` 同字段。success 时 `failed_command_id is None`；失败不得带 `durable_work`。用户文案不得原样转发 `Input should be ...`。

- [ ] **Step 1: Write the failing subgraph test**

In `test_agent_workflow_subgraph.py`, next to `CapturingToolRegistry`, add:

```python
class PartialLeadFollowUpToolRegistry(CapturingToolRegistry):
    async def execute(self, name, context, payload, *, policy):
        if name == "create_lead_follow_up":
            self.calls.append({"name": name, "context": context, "payload": payload, "policy": policy})
            raise CRMAPIClientError(
                "请求参数验证失败 (body -> method: Input should be '电话', '微信', '拜访', '邮件' or '其他')",
                status_code=422,
            )
        result = await super().execute(name, context, payload, policy=policy)
        if name == "create_lead":
            result.data = {
                "id": "lead_001",
                "public_id": "lead_001",
                "lead_name": "上海云图科技",
            }
        return result
```

Import `CRMAPIClientError` from `app.services.agent.tools.api_client`.

Add test (copy the waiting/confirm setup from `test_create_lead_with_follow_up_confirms_once_and_binds_created_lead_id`, swap registry):

```python
async def test_create_lead_follow_up_validation_failure_keeps_created_lead() -> None:
    parser = StaticSemanticParser(
        AgentSemanticParseResult.model_validate(
            {
                "intent": "CREATE_LEAD",
                "intent_confidence": 0.99,
                "lead": {
                    "lead_name": "上海云图科技",
                    "city": "上海",
                    "contact_name": "王敏",
                    "contact_phone": "13800138000",
                    "product_public_id": "prd_1",
                    "follow_up_content": "已确认需要安排产品演示",
                    "follow_up_method": "电话",
                },
            }
        )
    )
    tool_registry = PartialLeadFollowUpToolRegistry()
    interaction_resolver = CanonicalConfirmationResolver()
    orchestrator = RootOrchestrator(
        checkpointer=json_safe_checkpointer(),
        context_resolver=EmptyContextResolver(),
        decision_classifier=CreateStandaloneWriteDecisionClassifier(reason_code="CREATE_LEAD"),
        query_executor=FailingQueryExecutor(),
        interaction_resolver=interaction_resolver,
        workflow_subgraph=build_workflow_subgraph(
            planner=CRMWorkflowPlanner(
                semantic_parser=parser,
                temporal_resolver=FixedTemporalResolver(),
            ),
            effect_executor=CRMWorkflowEffectExecutor(tool_registry=tool_registry),
        ),
    )
    runtime = RootRuntimeContext(
        db=object(),
        authorization="Bearer test-token",
        metadata={"current_datetime": datetime(2026, 8, 23, 9, 0, 0)},
    )
    waiting = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=562,
            client_request_id="req_partial_lead_waiting",
            input=TextTurnInput(
                type="text",
                text="创建上海云图科技线索,联系人王敏,电话13800138000,已电话确认需要安排产品演示",
            ),
        ),
        runtime=runtime,
    )
    assert isinstance(waiting, WorkflowDispatchResult)
    interaction_resolver.continuation = waiting.continuation
    failed = await orchestrator.dispatch(
        RootTurnInput(
            team_id=1,
            user_id=2,
            session_id=562,
            client_request_id="req_partial_lead_confirmed",
            input=InteractionTurnInput(
                type="interaction",
                action_id="act_confirm_create_lead_with_follow_up",
            ),
        ),
        runtime=runtime,
    )
    assert isinstance(failed, WorkflowDispatchResult)
    assert isinstance(failed.workflow_result, WorkflowFailedResult)
    assert failed.workflow_result.retryable is False
    assert failed.workflow_result.failed_command_id == "create_lead_follow_up"
    assert [item.public_id for item in failed.workflow_result.committed_resources] == ["lead_001"]
    assert "Input should be" not in failed.workflow_result.message
    assert failed.workflow_result.message == (
        "已创建线索「上海云图科技」，但首次跟进没写上：跟进方式无效。\n"
        "请直接为这条线索补充跟进（电话 / 微信 / 拜访 / 邮件 / 其他），不要再创建同一条线索。"
    )
    assert [call["name"] for call in tool_registry.calls] == ["create_lead", "create_lead_follow_up"]
```

Also add a 5xx variant using `CRMAPIClientError("upstream", status_code=503)` on the second command: `retryable is True`, message remains `"CRM 服务暂时不可用, 请稍后重试。"` (existing executor copy), `committed_resources` still contains the lead.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd CRM-Server && pytest tests/unit/test_agent_workflow_subgraph.py::test_create_lead_follow_up_validation_failure_keeps_created_lead -q`

Expected: FAIL — `WorkflowFailedResult` has no `committed_resources`; message is the raw API string.

- [ ] **Step 3: Implement committed resources and user-facing copy**

In `contracts.py`:

```python
class WorkflowCommittedResource(WorkflowContractModel):
    command_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-z][a-z0-9_]*$")
    tool_name: str = Field(min_length=1, max_length=128, pattern=r"^[a-z][a-z0-9_]*$")
    resource: Literal["lead", "customer", "customer_activity", "contact", "opportunity"]
    public_id: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=200)
```

Add to `WorkflowEffectResult` and `WorkflowFailedResult`:

```python
    committed_resources: list[WorkflowCommittedResource] = Field(default_factory=list, max_length=20)
    failed_command_id: str | None = Field(default=None, min_length=1, max_length=128)
```

Update `WorkflowEffectResult.validate_outcome`:

```python
        if self.success:
            if self.code is not None:
                raise ValueError("successful Workflow effects cannot include an error code")
            if self.failed_command_id is not None:
                raise ValueError("successful Workflow effects cannot include a failed command")
        else:
            if self.code is None:
                raise ValueError("failed Workflow effects require an error code")
            if self.durable_work:
                raise ValueError("failed Workflow effects cannot publish durable-work receipts")
```

In `execution.py`, add resource mapping and copy helper. Keep existing retryable status helper.

```python
from typing import Literal

WorkflowCommittedKind = Literal["lead", "customer", "customer_activity", "contact", "opportunity"]
_TOOL_RESOURCE: dict[str, WorkflowCommittedKind] = {
    "create_lead": "lead",
    "create_customer": "customer",
    "create_customer_activity": "customer_activity",
    "create_contact": "contact",
    "create_opportunity": "opportunity",
}
_DISPLAY_KEYS = ("lead_name", "account_name", "title", "name", "display_name")


def _committed_resource(command: WorkflowCommand, data: object) -> WorkflowCommittedResource | None:
    resource = _TOOL_RESOURCE.get(command.tool_name)
    if resource is None or not isinstance(data, dict):
        return None
    public_id = data.get("public_id") or data.get("id")
    if not isinstance(public_id, (str, int)) or isinstance(public_id, bool):
        return None
    display_name = next(
        (
            str(data[key]).strip()
            for key in _DISPLAY_KEYS
            if isinstance(data.get(key), str) and str(data[key]).strip()
        ),
        str(public_id),
    )
    return WorkflowCommittedResource(
        command_id=command.command_id,
        tool_name=command.tool_name,
        resource=resource,
        public_id=str(public_id),
        display_name=display_name,
    )
```

User-facing copy:

```python
def _user_facing_effect_failure(
    *,
    command: WorkflowCommand,
    committed: list[WorkflowCommittedResource],
    retryable: bool,
    original: str,
) -> str:
    if retryable:
        return original
    if command.tool_name == "create_lead_follow_up" and committed:
        lead = committed[0]
        return (
            f"已创建线索「{lead.display_name}」，但首次跟进没写上：跟进方式无效。\n"
            "请直接为这条线索补充跟进（电话 / 微信 / 拜访 / 邮件 / 其他），不要再创建同一条线索。"
        )
    if command.tool_name == "create_customer_activity" and committed:
        customer = committed[0]
        return (
            f"已创建客户「{customer.display_name}」，但首次跟进没写上。\n"
            "请直接为这个客户记录跟进，不要再创建同一客户。"
        )
    if committed:
        names = "、".join(f"「{item.display_name}」" for item in committed)
        return f"已完成{names}，但后续写入没完成。请针对已有对象继续操作，不要重复创建。"
    return "操作没完成，确认已失效，请改数据后重新描述。"
```

For the method-invalid sentence: use it when `command.tool_name == "create_lead_follow_up"` and (`"method"` in original or `"跟进方式"` in original or original starts with `"请求参数验证失败"`). If the 4xx is some other follow-up field, still use the same lead-created / don't recreate copy but reason can be `"首次跟进没写上"` without `跟进方式无效`. Spec locks the method sentence for this screenshot path; the test above uses that exact original, so the first branch must match.

In `execute()` loop, initialize `committed: list[WorkflowCommittedResource] = []`. On `_execute_command` returning `WorkflowEffectResult`, return:

```python
            return result.model_copy(
                update={
                    "committed_resources": list(committed),
                    "failed_command_id": command.command_id,
                    "message": _user_facing_effect_failure(
                        command=command,
                        committed=committed,
                        retryable=result.retryable,
                        original=result.message,
                    ),
                }
            )
```

On success, append `_committed_resource(command, result.data)` when not None.

In `graph.py` `_execute` failed branch, pass `committed_resources=effect_result.committed_resources` and `failed_command_id=effect_result.failed_command_id` into `WorkflowFailedResult`.

Also update `CapturingToolRegistry` lead/customer success `data` to include `public_id` and `lead_name`/`account_name` so extraction works without changing payload assertions.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd CRM-Server && pytest tests/unit/test_agent_workflow_subgraph.py::test_create_lead_follow_up_validation_failure_keeps_created_lead tests/unit/test_agent_workflow_subgraph.py::test_create_lead_with_follow_up_confirms_once_and_binds_created_lead_id tests/unit/test_agent_workflow_subgraph.py::test_confirmed_workflow_returns_non_retryable_failure_when_guardrail_rejects_effect -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/app/services/agent/workflow/contracts.py CRM-Server/app/services/agent/workflow/execution.py CRM-Server/app/services/agent/workflow/graph.py CRM-Server/tests/unit/test_agent_workflow_subgraph.py
git commit -m "feat(agent): keep committed resources on confirmation write failure"
```

---

### Task 5: Retire confirmation action on non-retryable failure

**Files:**
- Modify: `CRM-Server/app/services/agent/application.py`
- Modify: `CRM-Server/tests/unit/test_agent_ui_application.py`

**Interfaces:**
- Consumes: `WorkflowFailedResult.retryable`.
- Produces: `_action_claim_succeeded` 对 `FAILED and retryable is False` 返回 True（complete）；`FAILED and retryable is True` 仍 False（release）。不把失败写成 `REVOKED`。

- [ ] **Step 1: Write the failing application test**

In `test_agent_ui_application.py`, copy `test_failed_workflow_releases_root_action_claim` and add:

```python
@pytest.mark.asyncio
async def test_non_retryable_failed_workflow_completes_root_action_claim(
    application_harness,
) -> None:
    service, session_factory = application_harness
    session_id, action_id = await _start_interaction(service)
    action_repository = AgentUIActionRepository()

    def claim_action(turn: RootTurnInput, runtime: RootRuntimeContext) -> None:
        action_repository.begin_consumption(
            runtime.db,
            public_id=action_id,
            team_id=turn.team_id,
            user_id=turn.user_id,
            session_id=turn.session_id,
            client_request_id=turn.client_request_id,
        )

    service.root_orchestrator = _FakeRootOrchestrator(
        WorkflowDispatchResult(
            decision=_decision("WORKFLOW", relation="CONTINUE_TASK"),
            workflow_result=WorkflowFailedResult(
                workflow_ref=WorkflowRef(workflow_id="wf_create_lead"),
                code="WORKFLOW_CRM_API_REJECTED",
                message=(
                    "已创建线索「上海云图科技」，但首次跟进没写上：跟进方式无效。\n"
                    "请直接为这条线索补充跟进（电话 / 微信 / 拜访 / 邮件 / 其他），不要再创建同一条线索。"
                ),
                retryable=False,
                progress=execution_progress(
                    confirmation_required=True,
                    has_supplements=False,
                    outcome="FAILED",
                ),
            ),
            action_claim_id=action_id,
        ),
        on_dispatch=claim_action,
    )

    await _collect(
        service,
        request_input=InteractionSubmissionInput(
            type="interaction_submission",
            action_id=action_id,
            values={"choice": "confirm"},
        ),
        client_request_id=UUID("aaa2e0e8-86d4-4d6c-a1b0-6490b2bf12be"),
        session_id=session_id,
    )

    with session_factory() as db:
        action = db.query(AgentUIAction).filter_by(public_id=action_id).one()
        assert action.status == AgentUIActionStatus.CONSUMED
        assert action.submitted_values == {"choice": "confirm"}
        assert action.result_message_id is not None
        assert action_repository.list_active_workflow_continuations(
            db,
            team_id=1,
            user_id=2,
            session_id=session_id,
        ) == []
```

Keep `test_failed_workflow_releases_root_action_claim` unchanged (`retryable=True` → ACTIVE).

If `list_active_workflow_continuations` signature differs, use the existing repository method from `CRM-Server/app/services/agent/ui/actions.py` (`team_id`, `user_id`, `session_id` as already used in production). Read that method’s parameters at implementation time and call them exactly; do not invent a fourth filter.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd CRM-Server && pytest tests/unit/test_agent_ui_application.py::test_non_retryable_failed_workflow_completes_root_action_claim tests/unit/test_agent_ui_application.py::test_failed_workflow_releases_root_action_claim -q`

Expected: FAIL — non-retryable FAILED currently releases to ACTIVE.

- [ ] **Step 3: Complete non-retryable FAILED claims**

Replace `_action_claim_succeeded` in `application.py` with:

```python
    @staticmethod
    def _action_claim_succeeded(dispatch: RootDispatchResult) -> bool:
        if not isinstance(dispatch, WorkflowDispatchResult):
            return False
        status = dispatch.workflow_result.status
        if status in {"WAITING", "COMPLETED", "CANCELLED", "SKIPPED"}:
            return True
        return status == "FAILED" and dispatch.workflow_result.retryable is False
```

Do not change `FailureDispatchResult` handling. Do not call `revoke`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd CRM-Server && pytest tests/unit/test_agent_ui_application.py::test_non_retryable_failed_workflow_completes_root_action_claim tests/unit/test_agent_ui_application.py::test_failed_workflow_releases_root_action_claim tests/unit/test_agent_ui_application.py::test_interaction_failure_releases_root_action_claim_and_hides_state_update_turn -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/app/services/agent/application.py CRM-Server/tests/unit/test_agent_ui_application.py
git commit -m "fix(agent): consume confirmation actions after non-retryable failure"
```

---

### Task 6: Rebind remaining writes to unique existing objects

**Files:**
- Modify: `CRM-Server/app/services/agent/workflow/planning.py`
- Modify: `CRM-Server/tests/unit/test_agent_lead_customer_product_fields.py`

**Interfaces:**
- Consumes: `lead_crud.get_by_name(db, lead_name, team_id)`；`customer_crud.get_by_name(db, account_name, team_id)`；only when `hasattr(db, "query")`.
- Produces: 唯一同名线索 + 非空 `follow_up_content` → 只 plan `create_lead_follow_up`，`lead_id=existing.public_id`，prompt `确认为已有线索“{name}”记录跟进吗?`；唯一同名线索且无跟进内容 → `WorkflowPlanningError` 文案 `线索「{name}」已存在，请直接补充跟进，不要重复创建。`；唯一同名客户 + 非空首次活动 → 只 plan `create_customer_activity` 绑定已有 `customer_id`。多候选或无 query 能力时保持原 create 路径。

- [ ] **Step 1: Write the failing planner tests**

Append to `test_agent_lead_customer_product_fields.py`:

```python
def test_plan_lead_follow_up_on_unique_existing_lead_does_not_recreate(monkeypatch):
    existing = SimpleNamespace(public_id="lead_existing", lead_name="A")
    monkeypatch.setattr(
        "app.services.agent.workflow.planning.lead_crud.get_by_name",
        lambda db, lead_name, team_id: existing,
    )
    db = SimpleNamespace(query=object())
    plan = _plan_lead(
        SimpleNamespace(
            **_lead_kwargs(product_public_id="prd_1"),
            follow_up_content="电话补充跟进",
            follow_up_method="电话",
        ),
        db=db,
    )
    assert [command.tool_name for command in plan.commands] == ["create_lead_follow_up"]
    assert plan.commands[0].payload["lead_id"] == "lead_existing"
    assert plan.interaction is not None
    assert plan.interaction.prompt == "确认为已有线索“A”记录跟进吗?"


def test_plan_lead_existing_without_follow_up_does_not_recreate(monkeypatch):
    existing = SimpleNamespace(public_id="lead_existing", lead_name="A")
    monkeypatch.setattr(
        "app.services.agent.workflow.planning.lead_crud.get_by_name",
        lambda db, lead_name, team_id: existing,
    )
    db = SimpleNamespace(query=object())
    from app.services.agent.workflow.planning import WorkflowPlanningError

    with pytest.raises(WorkflowPlanningError, match="已存在"):
        _plan_lead(SimpleNamespace(**_lead_kwargs(product_public_id="prd_1")), db=db)
```

Existing tests pass `db=object()` without `query` — planner must skip lookup when `not hasattr(db, "query")`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd CRM-Server && pytest tests/unit/test_agent_lead_customer_product_fields.py::test_plan_lead_follow_up_on_unique_existing_lead_does_not_recreate tests/unit/test_agent_lead_customer_product_fields.py::test_plan_lead_existing_without_follow_up_does_not_recreate -q`

Expected: FAIL — planner still emits `create_lead`.

- [ ] **Step 3: Implement unique-name rebind**

At top of `planning.py`:

```python
from app.crud.customer import customer_crud
from app.crud.lead import lead_crud
```

Add:

```python
    @staticmethod
    def _unique_named_record(getter, db: object, name: str, team_id: int):
        if not hasattr(db, "query"):
            return None
        return getter(db, name, team_id)
```

In `_plan_lead`, after `lead_name = str(lead["lead_name"])`:

```python
        existing_lead = self._unique_named_record(lead_crud.get_by_name, db, lead_name, team_id)
        follow_up_content = getattr(lead_model, "follow_up_content", None)
        if existing_lead is not None and (
            not isinstance(follow_up_content, str) or not follow_up_content.strip()
        ):
            raise WorkflowPlanningError(
                "WORKFLOW_LEAD_ALREADY_EXISTS",
                f"线索「{lead_name}」已存在，请直接补充跟进，不要重复创建。",
            )
```

If `existing_lead is not None` and follow-up content exists, skip `create_lead` and return `_confirmation_commands_plan` with a single `create_lead_follow_up` command, payload including `"lead_id": existing_lead.public_id`, prompt exactly `确认为已有线索“{lead_name}”记录跟进吗?`, facts include lead_name and follow-up fields.

`create_lead_follow_up` bindings that copy `lead_id` from `create_lead` must not be used on this path; set `lead_id` directly.

Mirror in `_plan_customer` with `customer_crud.get_by_name` and `account_name`. Unique existing customer + activity → only `create_customer_activity` with `customer_id=existing.public_id`. Unique existing customer + no activity → `WorkflowPlanningError` with `客户「{name}」已存在，请直接记录跟进，不要重复创建。` Do not emit `create_customer` when `existing` is found.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd CRM-Server && pytest tests/unit/test_agent_lead_customer_product_fields.py tests/unit/test_agent_workflow_subgraph.py::test_create_lead_with_follow_up_confirms_once_and_binds_created_lead_id tests/unit/test_agent_workflow_subgraph.py::test_create_customer_with_activity_confirms_once_and_binds_created_customer_id -q`

Expected: PASS. `db=object()` tests still create new leads.

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/app/services/agent/workflow/planning.py CRM-Server/tests/unit/test_agent_lead_customer_product_fields.py
git commit -m "feat(agent): bind follow-up writes to unique existing leads"
```

---

### Task 7: Unlock confirmation actions after the stream ends

**Files:**
- Modify: `CRM-Client/src/components/agent/agentInteractionState.ts`
- Create: `CRM-Client/src/components/agent/__tests__/agentInteractionState.test.ts`
- Modify: `CRM-Client/src/components/agent/CRMAgentChat.vue`

**Interfaces:**
- Consumes: existing `unlockInteraction` in `CRMAgentChat.vue`.
- Produces: `unlockInteractionActionId(locked: ReadonlySet<string>, actionId: string): Set<string>`；`submitInteraction` 在 `try/finally` 里解锁，包括 FAILED 和 transport error。

- [ ] **Step 1: Write the failing helper test**

Create `CRM-Client/src/components/agent/__tests__/agentInteractionState.test.ts`:

```typescript
import { describe, expect, it } from 'vitest'

import { unlockInteractionActionId } from '../agentInteractionState'

describe('unlockInteractionActionId', () => {
  it('removes the submitted action after a failed confirmation', () => {
    const locked = new Set(['act_confirm_lead'])
    expect(unlockInteractionActionId(locked, 'act_confirm_lead')).toEqual(new Set())
  })

  it('leaves unrelated locks in place', () => {
    const locked = new Set(['act_confirm_lead', 'act_other'])
    expect(unlockInteractionActionId(locked, 'act_confirm_lead')).toEqual(new Set(['act_other']))
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd CRM-Client && npm run test:unit -- src/components/agent/__tests__/agentInteractionState.test.ts`

Expected: FAIL — export missing.

- [ ] **Step 3: Implement helper and wire finally**

Append to `agentInteractionState.ts`:

```typescript
export function unlockInteractionActionId(
  locked: ReadonlySet<string>,
  actionId: string,
): Set<string> {
  return new Set([...locked].filter(item => item !== actionId))
}
```

In `CRMAgentChat.vue`, import `unlockInteractionActionId` from `agentInteractionState`. Change `unlockInteraction` to:

```typescript
const unlockInteraction = (actionId: string): void => {
  lockedInteractionActionIds.value = unlockInteractionActionId(
    lockedInteractionActionIds.value,
    actionId,
  )
}
```

Replace `submitInteraction` with:

```typescript
const submitInteraction = async (actionId: string, values: JsonObject): Promise<void> => {
  if (isCompactTaskCompletionAction(messages.value, actionId)) {
    await submitCompactTaskInteraction(actionId, values)
    return
  }
  if (isStreaming.value || lockedInteractionActionIds.value.has(actionId)) return
  lockedInteractionActionIds.value = new Set([...lockedInteractionActionIds.value, actionId])
  try {
    await submitInput(
      { type: 'interaction_submission', action_id: actionId, values },
      { label: '正在提交...' },
    )
  } finally {
    unlockInteraction(actionId)
  }
}
```

Do not change compact-task success/failure unlocking.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd CRM-Client && npm run test:unit -- src/components/agent/__tests__/agentInteractionState.test.ts src/components/agent-ui/__tests__/AgentUIInteractionBlock.test.ts`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add CRM-Client/src/components/agent/agentInteractionState.ts CRM-Client/src/components/agent/__tests__/agentInteractionState.test.ts CRM-Client/src/components/agent/CRMAgentChat.vue
git commit -m "fix(agent): unlock confirmation actions after submit settles"
```

---

### Task 8: Domain docs

**Files:**
- Modify: `CONTEXT.md`
- Modify: `CRM-Docs/design-agent/runtime/hitl-guardrails.md`
- Modify: `CRM-Docs/design-agent/runtime/interaction-policy.md`

**Interfaces:**
- Consumes: this plan’s invariants.
- Produces: 文档与运行时一致。不改 ADR 0001 / 0002。

- [ ] **Step 1: Update CONTEXT.md invariants**

Append after invariant 11:

```markdown
12. 确认写入在不可重试业务拒绝后必须退役该确认 continuation；已成功原子保留，剩余原子另开任务，不得重放已成功 create。
```

- [ ] **Step 2: Update HITL guardrails**

After the paragraph starting with `确认前 Agent 只能说明将要执行什么`, add:

```markdown
确认前 payload 必须通过对应 CRM 写入 schema 的闭世界校验。确认卡可以投影只读 facts，但不能用 facts 收集新字段。

确认执行失败分叉：

- 可重试依赖失败（5xx / 超时）：确认 action 放回 ACTIVE，只允许再点同一按钮重试同一 payload。
- 不可重试业务拒绝（4xx 校验等）：确认 action 标记 CONSUMED，不再占 active workflow；已成功 command 不回滚；用户必须开新任务补剩余原子。
```

- [ ] **Step 3: Update interaction policy**

After `不得在一条最终回复里同时要求用户确认、补字段、选择对象或决定建议。` add:

```markdown
确认卡上的只读 facts 不是第二个交互。写入失败反馈可以说明已创建对象，但同一轮不得再附一张新确认卡。
```

- [ ] **Step 4: Commit**

```bash
git add CONTEXT.md CRM-Docs/design-agent/runtime/hitl-guardrails.md CRM-Docs/design-agent/runtime/interaction-policy.md
git commit -m "docs(agent): record confirmed-write failure lifecycle invariants"
```

---

## Self-review

**Spec coverage:**
- §6 闭世界枚举 → Task 1–2
- §6.3 prompt / §6.4 tool → Task 2
- §7 facts → Task 3
- §8.1–8.2 committed + 文案 → Task 4
- §8.3 action ledger → Task 5
- §8.4 前端锁 → Task 7
- §9 已有对象改绑 → Task 6
- §11 文档 → Task 8
- §12 回归：现有 lead+follow-up subgraph 测试在 Task 2/3/4 重跑；retryable 5xx application 测试在 Task 5 保留

**Placeholders:** none.

**Type consistency:** `WorkflowConfirmationFact` / `InteractionConfirmationFact` / Zod fact 三字段同名；`WorkflowCommittedResource` 在 Effect 与 FailedResult 同字段；`unlockInteractionActionId` 被 `CRMAgentChat.unlockInteraction` 调用。

---

Plan complete and saved to `docs/superpowers/plans/2026-09-16-confirmed-write-lifecycle-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** — 每个 Task 派一个新 subagent，Task 之间我做 review。

**2. Inline Execution** — 本会话按 executing-plans 逐 Task 执行，设检查点。

Which approach?
