# 确认写入生命周期

- 日期：2026-09-16
- 状态：已确认，待实施
- 范围：所有 `CONFIRMATION_REQUIRED` 的 Workflow 写入，含线索+首次跟进、客户+首次活动、单 command 确认写入。不改 Query、商机建议独立原子、客户活动质量门禁。
- 上游决定：这是一次完整运行时切流，不是线索特例，也不是分期 MVP。四条契约同一合并门禁同时生效。确认等待仍只接受结构化按钮。组合写入保持独立原子、互不回滚。
- 相关规范：`docs/adr/0001-customer-activity-workflow-parity.md`、`docs/adr/0002-root-semantic-route-recovery.md`、`CRM-Docs/design-agent/foundations/architecture-boundary.md`、`CRM-Docs/design-agent/runtime/hitl-guardrails.md`、`CRM-Docs/design-agent/runtime/interaction-policy.md`、`CRM-Docs/design-agent/runtime/tools.md`
- 相关实现：`CRM-Server/app/services/agent/workflow/planning.py`、`CRM-Server/app/services/agent/workflow/execution.py`、`CRM-Server/app/services/agent/workflow/contracts.py`、`CRM-Server/app/services/agent/application.py`、`CRM-Server/app/services/agent/ui/actions.py`、`CRM-Server/app/services/agent/ui/composer.py`、`CRM-Server/app/services/agent/ui/schemas.py`、`CRM-Server/app/services/agent/tool_registry.py`、`CRM-Server/app/services/agent/prompts.py`、`CRM-Client/src/schemas/agent-contracts/ui-interactions.ts`、`CRM-Client/src/components/agent/CRMAgentChat.vue`、`CRM-Client/src/components/agent-ui/AgentUIInteractionBlock.vue`

## 1. 背景与目标

截图路径：用户提交完整「创建 Hifox 线索 + 首次跟进」→ 确认卡只问「确认要创建线索“协鑫数智科技”并记录首次跟进吗?」→ 点确认 → `create_lead_follow_up.method` 422（只接受 `电话/微信/拜访/邮件/其他`）→ 确认卡仍「待处理」且按钮灰 → 用户用文本补「电话…」整单重提，先后撞上 `ACTIVE_WORKFLOW_SWITCH_POLICY_INVALID` 和 `WORKFLOW_CONFIRMATION_REQUIRES_STRUCTURED_ACTION`。

根因不在 Root 语义，而在确认写入生命周期缺四件事：

1. Planner 把模型 `follow_up_method` 原样写入 command。空才兜底「其他」。Prompt 还允许 `线上会议/线下会议/会议`。`CreateLeadFollowUpInput.method` 是自由 `str`，要到 CRM API 才爆。
2. 确认交互禁止 `fields`，prompt 又不投影将写入的 method/正文，用户盲确认。
3. `WorkflowFailedResult` 无论是否可重试，application 都 `release_consumption`，action 回到 `ACTIVE`，继续占 `active_workflow`。前端 `submitInteraction` 把 action 锁进 `lockedInteractionActionIds` 后不解锁。
4. `create_lead` 与 `create_lead_follow_up` 是两次独立 API。第二步 422 时第一步已提交。失败文案是 API 校验句，不含已创建线索。幂等 key 绑 `workflow_id:command_id`，文本重提是新 workflow。

目标：所有确认写入共用同一套成熟契约。截图路径的合法终态只有两种：确认前 method 已是闭世界合法值并写完两条；或线索已创建、确认卡已退役、系统只允许补跟进、禁止再跑 `create_lead`。

## 2. 非目标

- 不把多 command 包进一个 DB 事务，不做补偿 saga。已冻结：客户/线索创建成功、后续跟进失败时主体保留。
- 不拆「确认等待只接受结构化 action」的门禁。纯文本不能 resume 确认卡。
- 不给线索首次跟进上客户活动那套质量评分 / 下一步门禁。Q-25 仍是产品项，本期只要求跟进内容非空、method 闭世界合法。
- 不把线索失败灌进客户活动 Workflow，也不把客户活动 `activity_kind` 倒回旧 `method`。
- 不把 `lead` 加进 `CRMResource` / Query catalog。部分成功对象用写入侧 `WorkflowCommittedResource`，不假装可查询。
- 不在 Root 用正则/关键词识别「电话」。纠错文本在确认卡退役后走普通 `SWITCH_TASK` 新规划。
- 不在确认卡上开可编辑表单。改字段走补充交互或新任务。
- 不改商机建议与活动写入的独立原子，不改待办 `COMPACT_TASK_COMPLETION` 的完成语义。

## 3. 方案选择

采用「规划期闭世界 + 可审确认事实 + 失败分叉退役 + 部分成功绑已有对象」。

放弃：

- 只修线索 method 和前端解锁：客户+活动、其它确认写入仍会在 422 后锁死。
- 组合写入改事务/saga：直接打 ADR 0001 独立原子。
- 确认等待中允许文本 resume：ADR 0002 和 HITL 明确禁止用自然语言代替按钮授权。
- 失败后仍保留 ACTIVE 确认卡让用户再点：会重放同一份非法 payload。

## 4. 不变量

1. **确认前 payload 必须能通过对应 CRM 写入 schema。** 非法枚举、必填空值不得生成 `CONFIRMATION_REQUIRED` plan。
2. **确认交互仍是 `confirm/cancel`。** 只读事实可以出现在同一张确认卡上，不能变成 `form`。
3. **一轮最终回复仍只有一个需要用户响应的交互。** 失败反馈可以带已创建对象说明，不能同时再塞一张新确认卡。
4. **可重试依赖失败（5xx / 超时 / 网络）必须把确认 action 放回 `ACTIVE`。** 按钮可再点，payload 不变。客户活动/商机现在依赖这条。
5. **不可重试业务拒绝（4xx 校验、权限拒绝、payload 非法）必须退役该确认 continuation。** action 不得再出现在 `list_active_workflow_continuations`。不得重放同一 payload。
6. **已成功 command 不回滚。** 失败文案必须列出已提交资源。后续纠错 plan 禁止再包含已成功的 create。
7. **确认等待期间，纯文本不得 resume 该 confirmation。** 退役之后，同一业务对象的纠错是新任务，不是旧 interrupt 的 supplement。

## 5. 分层职责

| 层 | 职责 | 禁止 |
|---|---|---|
| Prompt / 语义 schema | 闭世界枚举与 API 对齐；未知输出 `null` | 把 `线上会议` 写进 lead method 合法集合 |
| Planner | canonical 映射；映射失败 → `NeedsInput`；确认事实投影 | 把未校验 method 送进确认 |
| Tool input | `CreateLeadFollowUpInput.method` 用 `FollowUpMethod` | 自由 `str` 漏到 HTTP |
| CRM API | 最终权限、查重、事务 | Agent 直写业务表 |
| Effect executor | 顺序执行；记录已提交 command；失败带 `retryable` + committed | 失败时丢掉已成功结果 |
| Application / action ledger | 可重试 → release；不可重试 → complete | FAILED 一律 release |
| Root | 无 active confirmation 后按普通语义规划新任务 | 关键词认「电话」 |
| 前端 | 锁生命周期跟 ledger；流结束后按权威状态解锁 | 本地锁比服务端活得久 |

## 6. 规划期闭世界

新增确定性模块，供 Planner 和 tool schema 共用，不走模型：

```text
app/services/agent/workflow/write_enums.py
```

### 6.1 线索跟进方式

目标集合与 `app.models.lead.FollowUpMethod` 一致：`电话`、`微信`、`拜访`、`邮件`、`其他`。

| 输入 | 输出 |
|---|---|
| `null` / `""` / 空白 | `其他` |
| `电话` / `PHONE` / `phone` / `电话联系` / `电话沟通` / `来电` | `电话` |
| `微信` / `WECHAT` / `wechat` | `微信` |
| `拜访` / `VISIT` | `拜访` |
| `邮件` / `EMAIL` / `email` | `邮件` |
| `其他` / `OTHER` / `other` | `其他` |
| `会议` / `线上会议` / `线下会议` / `视频会议` | `其他` |
| 其它非空串 | 不可映射 → `WorkflowPlanningNeedsInput` |

不可映射时追问必须给出五选一，不得再让模型自由发挥。`_plan_lead` 在组装 `create_lead_follow_up` 之前调用；确认卡上的 method 必须是映射后的值。

客户活动继续 `infer_activity_kind`，不走这张 lead method 表。

### 6.2 公司规模

`CompanyScale` 可选。能唯一落入五个档位则写入对应中文枚举；不能则省略字段，不阻断确认，不 422。

`10~29`、`10-29`、`15人左右`、`1-50人` 唯一映射为 `1-50人`。不得把 `10~29` 原样写入 payload。

### 6.3 Prompt

`CRM-Server/app/services/agent/prompts.py` 里 lead 的 `follow_up_method` 改为：

```text
电话|微信|拜访|邮件|其他|null
```

删掉 `线上会议|线下会议|会议`。客户活动 prompt 已是五值，不动。最终仍以 Planner 为准。

### 6.4 Tool 第二道门

`CreateLeadFollowUpInput.method` 改为 `FollowUpMethod`，默认 `FollowUpMethod.OTHER`。Planner 漏网时在 tool 层变成 `WORKFLOW_PAYLOAD_INVALID`，不得再打到 CRM 校验句。这是防御，不是主路径。主路径必须在确认前拦住。

## 7. 可审确认事实

`WorkflowInteraction` 的 confirmation 继续禁止 `fields`（可编辑）。新增只读：

```text
class WorkflowConfirmationFact(WorkflowContractModel):
    key: str          # ^[a-z][a-z0-9_]*$
    label: str
    value: str        # 已 canonical 的展示值，不是模型原文
```

`WorkflowInteraction.facts: list[WorkflowConfirmationFact] = []`，仅 `confirmation` 允许非空。Composer 映射到 `InteractionBlock.facts`。前端 `ui-interactions.ts` 的 strict Zod 必须同步该字段，否则消息解析失败。确认卡在按钮上方只读渲染 facts。

线索+首次跟进必须投影：

| key | 来源 |
|---|---|
| `lead_name` | 线索名 |
| `contact_name` | 联系人 |
| `contact_phone` | 电话 |
| `city` | 城市 |
| `company_scale` | 有则显示 |
| `product` | 有则显示产品名或 public_id |
| `follow_up_method` | 映射后的 method |
| `follow_up_content` | 跟进正文 |
| `next_action` | 有则显示 |

prompt 可保留一句：「确认要创建线索“{name}”并记录首次跟进吗?」。用户看见的 method 必须与将 POST 的 method 相同。

客户+首次活动同样投影客户名、活动正文、`activity_kind`、下一步。其它单 command 确认至少投影业务对象名和将写入的关键字段；没有额外字段的可以 `facts=[]`。

不把 facts 做成第三种交互，不改变 `confirm/cancel` 授权模型。

## 8. 失败分叉与确认退役

### 8.1 Effect 结果

`WorkflowEffectResult` 失败时允许携带已提交证据（今天禁止 `durable_work` 的规则保留；新增 committed 资源，不是 post-commit job）：

```text
class WorkflowCommittedResource(WorkflowContractModel):
    command_id: str
    tool_name: str
    resource: Literal["lead", "customer", "customer_activity", "contact", "opportunity"]
    public_id: str
    display_name: str

class WorkflowEffectResult:
    success: bool
    code: str | None
    message: str
    retryable: bool = False
    durable_work: list[...] = []          # 仅 success
    committed_resources: list[WorkflowCommittedResource] = []
    failed_command_id: str | None = None
```

校验：

- success 时 `failed_command_id` 必须空，`committed_resources` 可空。
- 失败时必须有 `code`；`failed_command_id` 指向倒下的 command（若在执行前失败可为 `null`）。
- `committed_resources` 只含本 plan 已成功 command，按执行顺序。
- 失败仍不得带 `durable_work`。

`retryable` 沿用现口径：`status_code is None or in {408, 429} or >= 500`。4xx 校验、权限、payload 非法 → `retryable=False`。

Executor 在 command 循环里每成功一次就记下 `WorkflowCommittedResource`（从 tool `data` 取 `id`/`public_id`/`lead_name`/`account_name`）。失败 return 时带上已记录列表，不得丢。

### 8.2 Workflow 失败结果

`WorkflowFailedResult` 增加同样的 `committed_resources`、`failed_command_id`。`retryable` 已有。`message` 必须是用户可执行句，禁止原样转 API `Input should be ...`。

Composer 规则：

- 无 committed：说明操作没完成 + 可理解原因。不可重试时告诉用户确认卡已失效，请改数据后重新描述。
- 有 committed：先承认已创建对象，再说明失败 command 和原因，再给出剩余意图（只补跟进 / 只补活动），明确不要再创建同一主体。

线索+跟进、method 非法的标准句：

```text
已创建线索「协鑫数智科技」，但首次跟进没写上：跟进方式无效。
请直接为这条线索补充跟进（电话 / 微信 / 拜访 / 邮件 / 其他），不要再创建同一条线索。
```

### 8.3 Action ledger

改 `AgentApplicationService._action_claim_succeeded` / `_settle_action_claim`：

| dispatch | 处理 |
|---|---|
| WAITING / COMPLETED / CANCELLED / SKIPPED | 现逻辑：complete |
| FAILED 且 `retryable=True` | release → action 回 ACTIVE，按钮可再点 |
| FAILED 且 `retryable=False` | **complete**（不是 release，也不是 Case 那种业务撤销） |
| 其它 FailureDispatch | 现逻辑：release |

不可重试失败后：

- action `CONSUMED`，`submitted_values` 保留用户点过的 `confirm`
- 历史确认卡投影为 `SUBMITTED`（已提交），不是「待处理」，也不是「已取消」
- `list_active_workflow_continuations` 只看 `ACTIVE`，该卡不再是 `active_workflow`
- 下一轮纯文本不再命中 `WORKFLOW_CONFIRMATION_REQUIRES_STRUCTURED_ACTION`

可重试失败仍必须 release。回归：确认后 CRM 5xx，卡可再点，不误 complete。

不要把写失败映射成 `REVOKED`。`REVOKED` 留给待办 Case 取消；read projection 把 `REVOKED` 显示成「已取消」，会谎称用户没确认。

### 8.4 前端锁

`CRMAgentChat.submitInteraction` 与 compact task 对齐：流结束（success / FAILED / transport error / finally）后按权威消息解锁。

- 权威状态仍 `ACTIVE`（可重试失败）→ 解锁，按钮可点
- 权威状态 `SUBMITTED` / `EXPIRED` / `CANCELLED` / `READ_ONLY` → 解锁；非 ACTIVE 本身不可点
- 不得在 FAILED 后把 action 留在 `lockedInteractionActionIds`

`AgentUIInteractionBlock` 渲染 `facts`。`controlsDisabled` 逻辑不变。

## 9. 部分成功后的剩余写入

原 workflow 在不可重试失败后是终态 `FAILED`。同一轮不得再发第二张确认卡（交互策略：失败反馈已是本轮唯一用户可见结果）。

下一轮用户文本（补电话、整单重贴、只说记跟进）：

1. 已无 active confirmation → Root 按 ADR 0002 普通语义路由，允许 `SWITCH_TASK`
2. Planner 对 `CREATE_LEAD` + 非空 `follow_up_content` 增加查重预检：团队内线索名唯一命中已有线索时，**不得**再生成 `create_lead`。只生成 `create_lead_follow_up`，`lead_id` 绑已有 public_id，确认文案改为「确认为已有线索“{name}”记录跟进吗?」
3. 多条同名或查无 → 保持现有 API 查重/补字段行为，不猜测
4. 用户明确只要建线索、没有跟进内容 → 同名唯一已有线索时直接告知已存在，不重复创建

客户+首次活动对齐：客户已在、活动失败后，后续只 plan `create_customer_activity`，绑定已有 `customer_id`。客户创建 API 的「唯一已有客户可复用」保持不变。

幂等 key 继续 `{tool}:{session_id}:{workflow_id}:{command_id}`。跨 workflow 不去重；去重是 CRM 查重 + Planner 预检。不要在 Agent 做第二套线索身份。

`WorkflowCommittedResource` 只用于失败文案和审计，不自动 resume 旧 workflow，不写入 Query result set。

## 10. 截图路径在新契约下的轨迹

```text
用户提交完整线索+跟进
  → Planner 映射 method（空→其他；「电话联系」→电话；会议→其他；非法→先补字段）
  → 确认卡展示 facts（含 method=其他/电话 等）
  → 用户点确认
  → create_lead 201，create_lead_follow_up 用已映射 method
  → COMPLETED

若旧数据/漏网 422 仍发生：
  → FAILED retryable=false，committed=[线索]
  → 确认卡 CONSUMED / 已提交，不再占 active_workflow
  → 前端解锁
  → 用户再发「电话…」→ 新任务 → 只确认写跟进，不再 create_lead
```

## 11. 文档与领域词

实施时同步：

- `CONTEXT.md` 稳定不变量补一条：确认写入在不可重试业务拒绝后必须退役该确认 continuation；已成功原子保留，剩余原子另开任务，不得重放已成功 create。
- `CRM-Docs/design-agent/runtime/hitl-guardrails.md`：确认前 payload 闭世界；失败分叉（可重试 release / 不可重试 complete）；确认卡 facts 只读。
- `CRM-Docs/design-agent/runtime/interaction-policy.md`：确认 facts 不是第二个交互；失败反馈不得再附新确认卡。
- 不改 ADR 0001 / 0002 正文；本 spec 是它们的失败生命周期补全，不是覆盖。

## 12. 测试与验收

后端（现有 `test_agent_workflow_subgraph.py`、`test_agent_lead_customer_product_fields.py` 上加，不另起平行套件）：

1. `_plan_lead`：`follow_up_method=None` → command method=`其他`，确认 facts 含跟进方式=其他。
2. `_plan_lead`：`follow_up_method="线上会议"` → method=`其他`，允许确认。
3. `_plan_lead`：`follow_up_method="传真"` → `WorkflowPlanningNeedsInput`，无 confirmation plan。
4. `_plan_lead`：`company_scale="10~29"` → lead payload `company_scale="1-50人"`；不得原样下发 `10~29`。
5. 现有 `test_create_lead_with_follow_up_confirms_once_and_binds_created_lead_id` 仍绿；payload method 仍为「电话」；waiting interaction 含 facts。
6. 确认后第二 command 4xx：workflow FAILED、`retryable=False`、`committed_resources` 含 lead、`failed_command_id=create_lead_follow_up`；application complete 该 action；后续 `list_active_workflow_continuations` 为空。
7. 确认后 CRM 5xx：FAILED、`retryable=True`、action 仍 ACTIVE。
8. 同名唯一已有线索 + 用户带跟进内容：plan 只有 `create_lead_follow_up`，确认文案为已有线索。
9. 客户+活动：客户成功、活动失败 → 主体保留、确认卡退役、文案含已创建客户；不得回滚客户。
10. 客户活动低分、缺下一步、高置信自动执行、商机建议独立、待办完成确认：现有测试保持绿色。
11. 确认 WAITING 时纯文本仍澄清 `WORKFLOW_CONFIRMATION_REQUIRES_STRUCTURED_ACTION`。退役后同等文本可进入新 WORKFLOW。

前端：

1. `submitInteraction` 在 error / FAILED 后 `lockedInteractionActionIds` 不含该 action。
2. 确认卡渲染 facts；ACTIVE 可点，SUBMITTED 不可点。
3. compact task 成功/失败解锁语义不变。

验证命令：

```text
cd CRM-Server && pytest tests/unit/test_agent_workflow_subgraph.py tests/unit/test_agent_lead_customer_product_fields.py tests/unit/test_agent_ui_application.py -q
cd CRM-Client && npm run test:unit -- src/components/agent-ui src/components/agent src/schemas/agent-contracts
```

action claim 落点是 `tests/unit/test_agent_ui_application.py`。不新建一次性脚本。

## 13. 风险

- **会议→其他** 会丢「这是会议」的语义。换成交 `拜访` 会误写拜访记录。选「其他」是保守默认；用户可在确认 facts 里看见并取消。
- **规模省略**：`10~29` 若映射规则过严被丢弃，线索仍可建，只是缺规模。可接受。
- **同名线索预检**：误把不相关的同名线索当成「刚创建的那条」。必须「当前团队 + 精确线索名唯一命中」。多候选不自动绑。
- **complete 不可重试失败**：用户不能再点同一张卡。这是目标。可重试路径必须有测试锁住。
- **CreateLeadFollowUpInput 改枚举**：旧 checkpoint 里非法 method 的待确认 plan 确认后会在 tool 层失败并走新失败分叉，不再 422 卡死。不迁移历史 checkpoint。
- **facts 协议加字段**：旧客户端忽略未知字段会看不到摘要，但 `extra=forbid` 的前端 schema 必须同步，否则解析失败。前后端同一 PR 切流。

## 14. 合并门禁

一次发布必须同时具备：Planner 闭世界、确认 facts、失败分叉（含前端解锁）、部分成功文案 + 已有对象预检。缺一视为未完成，不允许「先解锁按钮、摘要下周再做」。
