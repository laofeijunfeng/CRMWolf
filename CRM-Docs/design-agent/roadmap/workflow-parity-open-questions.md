# 旧流程到新 Workflow：Parity 待确认事项分析

> **状态说明（2026-09-02）：**逐项产品确认已经收口。本文保留问题分析和确认过程，不再作为待提问清单。冻结后的权威实现方案见 [客户活动 Agent Workflow Parity 实施规格](./customer-activity-workflow-parity-spec.md)，验收用例见 [客户活动 Agent Workflow 验收矩阵](./customer-activity-workflow-acceptance-matrix.md)。后续不得重复询问本文已经冻结的产品规则。

- **分析日期：**2026-09-01
- **对应矩阵：**[legacy-workflow-parity-matrix.md](./legacy-workflow-parity-matrix.md)
- **分析基线：**旧流程 `5641fff^`；统一 Workflow 迁移提交 `5641fff`；当前生产入口 `get_root_orchestrator()`；当前 HEAD `aa788665`
- **文档阶段：**产品确认已收口；本文现在只保留历史分析、确认记录和实现缺口台账，不再指导重复提问。代码实施状态以[实施状态页](./customer-activity-workflow-implementation-status.md)为准。
- **文档目的：**把 parity matrix 中的“疑似遗漏”拆成可以逐项签字的确认项，避免在没有明确产品合同和 API 证据前直接补代码，或者只补“跟进质量评估”而再次遗漏上下游能力。

> 本文中的“当前没有接入”指当前生产调用链 `Root → native Workflow → CRMWorkflowPlanner → CRMWorkflowEffectExecutor` 中没有看到对应能力；如果能力仍存在于旧图、独立 domain graph 或 Tool Registry 中，不等于它已经进入新 Workflow 的生产路径。

## 1. 当前结论：需要先确认的不是一个节点，而是四条能力链

### 1.1 已经可以直接判定为生产路径回归

以下事项不是单纯“可能设计变更”，当前代码与旧流程/权威设计合同之间已经出现明确不一致，建议作为 P0 回归处理：

1. **跟进质量评估没有进入新 Workflow Planner。**当前 `CRMWorkflowPlanner._plan_customer_activity()` 只检查 `follow_up.content`，没有注入 `AgentFollowUpQualityEvaluator`，也没有分数、六大原则、`missing_aspects` 或质量补充问题。
2. **下一步行动不是创建前门禁。**当前只有在 `next_action` 非空时把字段放入 payload；没有时仍可能因为 `intent_confidence >= 0.85` 自动创建跟进。
3. **质量补充后的重新质检链路不存在。**通用 `plan → await_required_input → apply_supplement → plan` 存在，但它只能补普通字段；因为 Planner 没有质量节点，所以无法做到“补充后重新解析、重新评分、再次判断是否允许写入”。
4. **跟进后的客户上下文和业务建议没有进入当前生产 Workflow。**旧流程有客户上下文读取和建议生成；当前 Root 生产装配只创建 `CRMWorkflowPlanner` 与 `CRMWorkflowEffectExecutor`，没有装配旧 `BusinessContextGraphService` / `AgentSuggestionGenerator` 等对应链路。
5. **`PAYMENT_RECORD` 在统一 Planner 中无分支。**语义合同、Tool Registry 和旧 `PaymentRecordPlanningGraphService` 仍存在，但当前 `CRMWorkflowPlanner.plan()` 没有 `PAYMENT_RECORD` 分支，最终会落到 `WORKFLOW_ACTION_UNSUPPORTED`。是否属于本期范围仍需产品确认，但“当前 Workflow 不支持”这一事实已经确认。

### 1.2 不能仅凭当前 Planner 缺少代码定性为回归

以下事项需要产品、架构或 API 验收证据后再分类：

- 创建客户/线索前的重复检查是否已由 CRM API 完整承接；
- `source_content` 是否允许使用语义解析后的规范化内容；
- `method` 是否已经由 `activity_kind` 完全替代；
- memory/current customer 是否是有意收紧为 Root 的显式实体引用；
- Query 与 Workflow 是否有意拆成两轮；
- durable work 是否已完整承接旧 post-write 链路，特别是任务投影；
- payment、License、payment plan 等动作是否纳入本期统一 Workflow。

### 1.3 若只修质量节点，仍然会留下的闭环缺口

即使立即接回质量评估，以下问题仍会存在：

```text
低质量补充后的 checkpoint 状态
客户选择与质量补充的交互优先级
客户上下文读取
建议生成与建议过滤
跟进后的二级动作确认
next task projection
PAYMENT_RECORD 统一入口
source_content / activity_kind 数据契约
重复检查和创建 API parity
trace / progress / durable work 的可观测性
```

因此建议先完成本文确认，再进入实现拆票。

---

## 2. 状态和决策标签

| 标签 | 含义 | 处理原则 |
|---|---|---|
| `CONFIRMED_REGRESSION` | 旧流程或权威设计明确要求，当前生产路径明确缺失或行为错误 | 不需要等产品重新决定是否存在；需要确认实现细节和验收样例，然后修复 |
| `PRODUCT_DECISION_REQUIRED` | 存在多个合理产品行为，代码无法推导唯一答案 | 先让产品/业务负责人确定合同，再实现 |
| `API_PARITY_VERIFICATION_REQUIRED` | 可能已由 CRM API、查询 Runtime 或 durable worker 承接，但当前静态代码不足以证明 | 先做公共 API/数据库/后台任务验收，不能只看 Tool 是否存在 |
| `INTENTIONAL_DESIGN_CHANGE_CANDIDATE` | 新架构可能有意改变旧行为，通常涉及安全、checkpoint 或 Query/Workflow 边界 | 需要记录 ADR/设计决策；没有决策记录前不要当作已完成迁移 |
| `OUT_OF_SCOPE_CANDIDATE` | 旧能力真实存在，但可能不属于本期统一 Workflow 范围 | 需要明确“保留旧入口/独立 Workflow/延期”的承接方和日期，不能默认为已迁移 |

优先级：

- **P0：**可能错误写入、绕过质量门禁、丢失关键收入/回款能力，或阻塞主业务闭环。
- **P1：**跟进可以写入，但无法形成客户理解、建议和下一步动作闭环。
- **P2：**数据契约、兼容性、后台恢复和审计等 parity 问题。
- **P3：**用户可见进度、追踪字段和运营报表等完善项。

---

## 2A. 本轮已冻结的产品决策（以对话确认为准）

以下结论已经逐项确认，后续只做代码/API/测试核对，**不再作为产品问题重复询问**。

### 活动范围与原子性

- 本期只处理客户下的跟进记录、会议纪要、商机创建和商机阶段推进。
- 不实现创建线索、回款、合同等其他业务动作。
- 跟进记录和会议纪要只有新增、删除，没有修改。
- 跟进、会议纪要、客户、商机保持独立原子性，不互相绑定回滚。
- 商机动作不混入跟进记录处理流程。
- 页面前端保持现有展示和交互方式。

### 活动内容与类型

- `source_content` 只保存用户原始输入；多轮补充时追加用户后续补充原文。
- 不把 Agent 提问、系统提示、评分理由或语义解析后的规范化内容写入 `source_content`。
- `activity_kind` 完全替代旧 `method`。
- 旧数据一次性迁移后不保留旧映射关系，不继续增加兼容历史债。
- 只保存最终评分，不保存同一条记录的评分过程、评分历史或中间分数。

### 评分与下一步行动

- Agent 和页面表单共用同一个 canonical 活动整理/评分入口。
- Agent 已完成整理和评分后直接写入最终结果，不再写入后重复评分。
- 页面表单先保存，再通过 durable 后台任务整理、评分并执行现有后续任务。
- 评分低于 60 分不允许 Agent 写入，评分失败/超时/结构化失败也不允许 Agent 写入。
- 页面表单评分失败不回滚已保存记录，保留失败状态并支持重试。
- 用户没有提到下一步行动时，Agent 需要追问。
- 用户明确暂时没有下一步时允许保存，但需要原因或复查条件。
- “继续跟进”“再看看”“保持联系”等模糊表达不能直接作为有效下一步行动。
- 明确动作但没有时间可以保存，不猜具体日期；明确时间时继续现有后台任务投影。

### 客户识别、记忆与创建

- 未完成 Workflow 的 checkpoint 有可信 `customer_id` 时直接复用，不重新搜索、不重新询问；只有用户明确切换客户时才清除绑定。
- 已完成会话在只有一个明确确认客户时可以自动承接；多个客户或语义不明确时才询问。
- 长期记忆只辅助理解和建议，不能直接授权本次写入；写入前仍做服务端权限/存在性校验。
- 搜不到客户时直接告知“没有匹配客户”，不自动创建客户。
- 只有用户明确要求创建客户且必填信息完整时才调用客户创建 API。
- 客户重复由客户创建 API 处理；API 返回唯一已有客户时可以复用，多候选时才需要用户介入。
- 创建客户与首次跟进是两个独立原子操作；客户创建成功但跟进质量不通过时保留客户，不写跟进，等待补充。

### 商机

- 只实现商机创建和商机阶段推进。
- 已有商机与本次语义高置信度匹配时直接判定为已有商机，忽略重复创建，不强制用户确认。
- 仅提到已有商机不自动推进；只有明确要求推进时才生成独立推进建议。
- 明确出现新商机且没有匹配时，跟进先保存，再输出创建建议。
- 创建建议使用 Agent UI 的“是/否”组件；用户选择“是”后在 Agent 页面内嵌表单补充商机信息；弃用旧重型弹窗。
- 用户拒绝、取消或暂不处理商机建议不影响跟进；未处理建议保留为待处理，不阻塞主流程、不自动执行。
- 商机状态在提交时已发生变化：静默忽略过期操作，不覆盖、不重复执行、不提示用户。

### 后台任务、删除与可观测性

- 后台任务必须异步返回，不等待后台完成。
- 页面表单保存后进入 durable 后台任务；失败不回滚主记录，自动重试，基于同一记录和版本幂等恢复。
- 客户智能刷新、商机建议和现有任务投影属于独立后台动作，互不阻塞、互不影响。
- 删除跟进记录或会议纪要沿用现有删除机制，不新增“删除评分”操作；已有历史记录不用重新处理。
- 删除后的记录不再接受整理、评分、商机建议或其他后台结果写回。
- 前端沿用现有展示方式，后台状态只在必要时展示，不把异步处理伪装成同步完成。
- 内部保留关键决策 trace，不记录评分过程或评分历史；checkpoint 只保存恢复所需的最新 JSON-safe 状态，不保存模型临时推理。

### 仍需做的不是产品确认，而是实现核对

1. canonical evaluator 是否真正成为 Agent 和页面表单的唯一评分入口。
2. 页面表单是否已经去掉 `asyncio.create_task(process/evaluate)` 等旧入口，只保留 durable worker。
3. 旧 post-write effects 是否逐项映射到新的 durable worker，包括任务投影、客户智能刷新、商机建议和失败重试。
4. 客户创建、商机创建及阶段推进 API 是否提供最终的重复保护、权限校验和幂等保证。
5. 商机状态变化的静默跳过是否覆盖 planner、executor、tool/API 和前端投影所有层。
6. `source_content`、`activity_kind`、评分最终字段和迁移脚本是否已经完全消除旧路径依赖。
7. 取消、拒绝、切换、超时、过期和重试耗尽等终态是否能正确恢复、审计且不重复写入。

## 2B. 产品确认收口后的实现缺口台账

截至 2026 年 9 月 1 日，当前范围内的产品行为已经通过对话确认。下面这些不再作为待确认问题，而是进入代码/API/测试核对与实现阶段。

### A. 必须修改的生产路径缺口

| 编号 | 缺口 | 当前证据 | 目标行为 | 优先级 |
|---|---|---|---|---:|
| I-01 | Agent Planner 没有活动质量门禁 | `CRMWorkflowPlanner._plan_customer_activity()` 直接组装写入 payload，只判断内容和意图置信度 | 写入 command 生成前完成整理、下一步行动门禁和统一评分；`<60` 或评估失败不得生成写入计划 | P0 |
| I-02 | Agent 写入后仍触发页面表单式整理/评分 | `CustomerAIConfirmedWriteService.create_customer_activity()` 创建后调用 `trigger_processing()` | Agent 携带最终整理结果和最终评分一次性写入；不再进入二次整理/评分 | P0 |
| I-03 | Agent 与页面表单使用两套 evaluator | `AgentFollowUpQualityEvaluator` 与 `ActivityEvaluationAgent` 并存 | 提取一个 canonical evaluator；Agent 和 durable worker 只通过同一入口调用 | P0 |
| I-04 | 页面表单同时存在 durable job 和进程内 AI 任务入口 | 表单路径会创建 post-commit job，同时调用 `trigger_processing()`/`trigger_evaluation()` | 表单只落库并创建可恢复 durable AI job；接口立即返回，worker 负责整理、评分和后续投影 | P0 |
| I-05 | `source_content` 取了语义规范化内容 | Planner 使用 `follow_up.content` 作为 `source_content` | 从 checkpoint/turn input 取得用户原文；补充只追加用户原文；整理结果写 `content_json` 等字段 | P0 |
| I-06 | 下一步行动没有成为独立门禁 | Planner 只在有值时写入 `next_action`，无值仍可能自动执行 | 无下一步先追问；模糊行动不能通过；明确暂无下一步时要求原因或复查条件 | P0 |
| I-07 | 补充后没有质量重算闭环 | 通用 supplement 可重新 plan，但 Planner 没有质量节点 | 每次用户补充后重新 parse、整理、行动检查、评分，再决定是否写入 | P0 |
| I-08 | 商机建议没有进入活动 post-commit 主链 | 当前 `CustomerActivityPostCommitWorkflow` 主要覆盖任务投影、确认事项和客户智能刷新，未发现商机建议生成/投影 | 活动写入成功后独立异步生成商机建议；不阻塞活动，不自动执行二级动作 | P1 |
| I-09 | 商机状态过期仍返回用户提示 | 执行器 `WORKFLOW_RESOURCE_STALE` 当前消息要求重新发起操作 | 对已变化状态静默跳过；不覆盖、不重复执行、不提示用户 | P1 |

### B. 必须完成的 API/后台链路核对

| 编号 | 核对项 | 核对标准 |
|---|---|---|
| V-01 | 客户创建 API | 明确创建时由 API 负责字段校验、权限、重复保护、并发安全；唯一已有客户可复用，多候选才中断 |
| V-02 | 商机创建 API | 具备最终幂等、权限和重复保护；Agent 的语义匹配只是候选判断，不是最终事实 |
| V-03 | 商机阶段推进 API | 等待用户期间重新读取最新商机/阶段；状态已变化时返回可识别的 skipped，而不是普通错误 |
| V-04 | durable post-commit 链路 | 任务投影、客户智能刷新、商机建议分别有 durable operation、版本 fence、lease/retry 和幂等键 |
| V-05 | 删除竞态 | 活动删除后所有 AI 整理、评分、建议和投影均能在写入前被版本/存在性检查拦截 |
| V-06 | 旧字段依赖 | 迁移后查询、报表、序列化、API 和测试均只依赖 `activity_kind`，不残留 `method` 映射读取 |

### C. 必须补齐的验收测试

1. Agent 路径评分 59 分：不创建跟进，不触发商机建议。
2. Agent 路径低分补充后通过：只创建一条跟进，只落最终评分，不发生二次评分。
3. 无下一步、模糊下一步、明确暂无下一步三类输入分别符合门禁规则。
4. 页面表单提交立即返回；服务重启后 durable worker 仍能完成整理、评分和既有 post-write 链路。
5. 页面表单评分失败保留主记录，可重试且不重复创建记录。
6. Agent 的 `source_content` 只包含用户原文和用户补充，不包含 Agent/system 文本。
7. 已绑定客户的补充轮次不重复搜索；明确切换客户时重新解析并校验权限。
8. 高置信度匹配已有商机时不创建重复商机；明确新商机才生成建议。
9. 商机建议拒绝/取消/未处理不影响跟进；商机操作与跟进不共用回滚。
10. 商机状态变化时操作静默 skipped，不覆盖、不重试、不提示。
11. 删除跟进或会议纪要后，迟到的整理、评分、建议和投影全部无副作用。
12. durable job 重复领取、租约过期、重试耗尽和重复恢复均保持幂等。

### D. 实施顺序

```text
1. 冻结 canonical 活动整理/评分契约和 Workflow checkpoint 字段
2. 接入 Agent 质量门禁、下一步行动门禁和补充重规划
3. 改造 Agent 写入：最终整理+最终评分一次性写入，移除二次评分入口
4. 改造页面表单：只走 durable AI worker，保留失败重试和现有 post-write 投影
5. 接入独立商机建议 worker；接入商机创建/阶段推进 UI action
6. 修正商机过期状态为静默 skipped
7. 完成旧字段迁移后的全仓依赖清理
8. 按上述验收场景补单元、集成、恢复和并发测试
```

**结论：**现在已经不是“继续确认产品方案”的阶段，而是“按 I/V/T 台账逐项实现和验收”的阶段。除非代码核对发现真实 API 合同与上述已确认行为冲突，否则不再新增产品问题。

## 3. P0：跟进写入前的质量和安全门禁

### Q-01 跟进质量评估应该放在客户识别前还是后？

> **实施核对结论（2026-09-03）：已冻结，不再作为待确认项。**按权威 parity spec 和已确认的用户流程，实际顺序为：
> `语义理解 → 客户解析与跨轮绑定 → 内容整理 → 质量评分 → 下一步行动门禁 → 写入`。
> 客户解析在最前面是为了先确认活动归属；质量评估仍发生在任何写入之前。低质量时只产生一个补充交互，不创建活动或商机建议。

- **优先级：**P0
- **当前建议标签：**`CONFIRMED_IMPLEMENTATION`（“必须有质量门禁”本身是 `CONFIRMED_REGRESSION`）
- **关联能力：**质量评估顺序、隐私/权限边界、客户搜索成本、低质量补充交互。

**旧流程证据**

旧主图有独立 `evaluate_follow_up_quality` 节点，并在客户搜索之后由 `_route_after_customer_search()` 路由进入；旧质量 graph 本身的 preflight 又要求单一客户。也就是说，旧代码实际顺序接近：

```text
semantic_parse → customer_search → evaluate_follow_up_quality → customer_context
```

**新规则证据**

`CRM-Docs/design-agent/runtime/follow-up-quality.md` 明确写的是：

```text
语义解析 → 质量评估 → 客户搜索 → 客户上下文 → 写入确认
```

并规定质检不通过时本轮只问一个补充问题，不创建跟进、不输出商机建议。

**当前 Workflow 证据**

`CRMWorkflowPlanner.plan()` 当前先调用 `_plan_customer_activity()`，该方法先 `_resolve_customer()`，之后只检查 `follow_up.content`；没有质量 evaluator。当前生产装配 `runtime.py` 也没有把质量 evaluator 或质量 domain graph 注入 Planner。

**必须确认的问题**

1. 以设计文档为准，质量评估是否必须在客户识别前执行？
2. 质量评估是否允许使用客户上下文？若允许，哪些字段可以用？
3. 无法识别客户时，是否先对内容做质量评估，还是客户不确定时直接先选择客户？
4. 低质量时是否绝对不读取客户上下文，以避免无必要的权限访问和额外成本？
5. 质量评估失败时，是阻塞写入，还是降级为普通字段补充？

**推荐默认答案**

采用：

```text
语义解析 → 质量评估 → 客户识别 → 客户上下文 → 写入确认/执行
```

质量评估只依赖用户原文和语义结果，不直接访问业务表；通过后才执行客户解析/上下文读取。若产品认为客户上下文能显著提升事实判断，应单独定义“只读、已授权、不可泄露”的上下文输入合同，而不是让 evaluator 自由查库。

**不确认的风险**

- 可能重复实现一条与旧代码顺序不同的流程；
- 低质量输入可能先触发客户搜索和业务上下文读取；
- 同轮同时出现“选客户”和“补质量”两个交互，违反单一交互原则；
- 质量 evaluator 的输入契约在实现后再次返工。

**实施影响**

需要明确 Workflow state 中至少包含：`semantic_result`、`quality_result`、`quality_metadata`、`quality_block_reason`、客户候选和当前唯一交互。质量门禁应位于任何 `create_customer_activity` command 生成前。

**验收证据**

- 低质量但客户名称明确：只返回唯一质量补充问题，不调用客户上下文、不生成写入计划。
- 高质量但客户不唯一：只要求选择客户，不再要求质量补充。
- 质量 evaluator 失败：无 CRM 写入，无商机/回款建议，trace 中有失败原因。

---

### Q-02 `next_action` 是否是绝对必填？

- **优先级：**P0
- **当前建议标签：**`PRODUCT_DECISION_REQUIRED`
- **关联能力：**跟进闭环、任务生成、自动执行安全阈值。

**旧流程/规则证据**

旧质量评估使用“动作闭环原则”，设计文档要求低于 60 分时补充最关键缺失点；`interaction-policy.md` 还明确把跟进质量低于 60 分作为优先交互。

**当前 Workflow 证据**

`_plan_customer_activity()` 只在 `next_action` 非空时加入 payload；没有 `next_action` 时不会触发 `WorkflowPlanningNeedsInput`。后续判断只使用 `intent_confidence >= 0.85`，因此“意图高置信度”被错误地当成“跟进闭环完整”。现有 `test_create_follow_up_workflow_auto_executes_high_confidence_low_risk_action` 还把这种行为作为当前测试合同。

**必须确认的问题**

1. 每条跟进是否必须有明确的下一步行动？
2. “继续跟进”“持续关注”“再看看”是否算具体行动，还是仍需追问动作对象、责任人或时间？
3. `next_action` 是否必须配合 `next_follow_time`？
4. “客户暂无下一步”“等待客户内部决定”“项目暂缓”是否允许作为有效终态？
5. 用户明确说“暂无下一步”时，系统应：
   - 允许写入并记录无下一步原因；
   - 继续追问原因/责任人/复查时间；
   - 阻止写入。

**推荐默认答案**

- 默认要求可执行、可交接的下一步行动；
- 允许“暂无下一步”作为显式业务状态，但必须记录原因或复查条件，不能把它当成普通 `next_action`；
- 是否强制时间字段应按业务场景拆分：明确承诺/任务类需要时间，纯事实同步可允许没有时间，但不得没有闭环状态；
- `next_action` 文本应通过质量 evaluator 和代码层规则共同判断，不能只检查非空字符串。

**不确认的风险**

- 继续产生“记了一笔但没有下一步”的流水账；
- 自动执行路径会绕过业务闭环；
- 后续 next task projection 没有可靠 source；
- 测试会把错误行为固化为回归基线。

**实施影响**

需要区分至少三种状态：

```text
ACTIONABLE_NEXT_STEP
NO_NEXT_STEP_EXPLICITLY_STATED
NEXT_STEP_MISSING_OR_TOO_VAGUE
```

需要决定它们分别对应 `CREATE`、`NEEDS_INPUT` 还是 `CONFIRMATION`，并同步更新 semantic schema、质量结果、活动 payload 和任务投影合同。

**验收证据**

- “已沟通，客户再看看”不能自动写入；
- “已沟通，客户将在 9 月 5 日前确认预算，我于 9 月 6 日回访”可以通过；
- “客户暂缓，原因是预算冻结，10 月 1 日重新评估”按产品确认的显式无动作状态写入；
- “继续跟进”单独输入必须按产品决定进入补充或确认，不得静默视为完整行动。

---

### Q-03 低质量分数阈值和结果字段如何落地？

- **优先级：**P0
- **当前建议标签：**`CONFIRMED_REGRESSION` + `PRODUCT_DECISION_REQUIRED`（实现阈值已有设计，异常和持久化策略仍需决策）

**权威规则**

`follow-up-quality.md` 已明确：六大原则总分 100，`score >= 60` 通过，`score < 60` 不通过；代码层必须按 60 分重新归一化，不能只相信模型的 `passed`。

**当前缺口**

新 Workflow 没有质量结果，因此以下字段都没有生产消费：

```text
score
passed
reason
missing_aspects
supplement_question
suggested_revision
principle_scores
quality_source / model / fallback metadata
```

**必须确认的问题**

1. `60` 是否继续作为硬阈值？
2. 若模型输出 `score=80, passed=false`，代码是否强制按分数改为通过？
3. evaluator 超时、模型结构化输出失败或 fallback 失败时，是否 fail-closed？
4. `suggested_revision` 是仅展示给用户，还是允许直接作为待写入内容？
5. 质量结果是否进入活动表、Agent trace、checkpoint，还是单独质量表？
6. 是否需要保存每次补充前后的评分，而不是只保留最后一次？

**推荐默认答案**

- `score >= 60` 是代码硬门禁；
- `passed` 只作模型输出参考；
- evaluator 失败时 fail-closed，不写入；
- `suggested_revision` 不得未经用户确认替换原文；
- 至少保存 checkpoint + trace；质量分不应伪装成 CRM 活动事实；
- 保存每次评估的 metadata，便于回放和判断用户补充是否真正改善质量。

**实施影响**

需要一个纯业务门禁函数，例如根据结构化 evaluator result 产出：

```text
quality_status = PASSED | NEEDS_SUPPLEMENT | FAILED
write_allowed = true | false
interaction = one optional supplement question
```

该函数应独立于 CRM tool，便于单元测试和重放。

**验收证据**

- 分数 59：阻塞并只问一个问题；
- 分数 60：通过质量门禁；
- `passed` 与分数矛盾：按分数裁决；
- evaluator 异常：不创建、不生成建议；
- fallback 结果：有来源和错误原因，且仍经过相同阈值。

---

### Q-04 低质量补充与客户选择/写入确认的交互优先级是什么？

- **优先级：**P0
- **当前建议标签：**`CONFIRMED_REGRESSION`

**权威规则**

`interaction-policy.md` 要求同一轮最终回复只能有一个需要用户响应的动作，并规定质量低于 60 时先补跟进质量。`follow-up-quality.md` 明确低质量时本轮只展示补充问题。

**当前风险**

新 Workflow 的通用补充机制可以在客户缺失、字段缺失和确认之间切换，但没有质量动作类型，无法保证质量补充优先于客户选择、字段补充和确认。

**必须确认的问题**

1. 低质量时是否严格只问一个质量问题？
2. 是否禁止同时显示客户候选、写入确认、下一步建议？
3. 若低质量同时客户不唯一，是否先问质量还是先选客户？
4. 若用户回复同时包含质量信息和客户选择，是否允许一次性消费，还是仍拆为一个交互动作？
5. 质量补充的 `interaction_type`、`business_action`、恢复标识如何命名？

**推荐默认答案**

采用固定优先级：

```text
语义澄清
→ 质量补充
→ 客户选择
→ 必填字段补充
→ 写入确认
→ 写入结果
→ 二级建议确认
```

质量不通过时，其他信息可以在 checkpoint 中保留为候选，但不得在当前最终回复中要求用户做第二个决定。

**实施影响**

需要扩展 Workflow interaction 合同，使质量补充能被 interrupt/resume 明确表达；前端不应通过猜测文本区分“质量补充”和“普通字段补充”。

**验收证据**

检查一次低质量且客户候选多个的输入：最终回复只有一个问题；事件/trace 可说明客户候选已保留但未向用户展示为当前动作。

---

### Q-05 用户补充后是否重新执行全部前置步骤？

- **优先级：**P0
- **当前建议标签：**`CONFIRMED_REGRESSION` + `PRODUCT_DECISION_REQUIRED`（是否全量重算需要确认，不能复用旧质量结果是强建议）

**当前机制**

新 Workflow 已有：

```text
plan → await_required_input → apply_supplement → plan
```

但当前 Planner 只把补充文本重新拼回原始文本后重新做语义解析，没有质量结果的 checkpoint 状态或重新质检节点。

**必须确认的问题**

用户补充后是否必须重新执行：

```text
semantic parse
→ quality evaluation
→ customer resolution
→ customer context
→ action plan
```

以及：

1. 是否可以复用已确认的客户实体？
2. 如果补充改变了客户名称，是否以最新明确客户为准？
3. 如果补充改变了下一步行动或时间，是否覆盖原草稿？
4. 原质量结果和新质量结果是否都保留？
5. 用户补充内容是否应视为原文的一部分，还是独立 supplement evidence？

**推荐默认答案**

重新执行语义解析和质量评估；客户实体可以在满足“同一 pending 任务、无冲突、来自服务端已签发引用”的条件下复用，但仍应做权威 revalidation。任何会影响客户、事实、行动、时间或建议的补充，都必须刷新后续计算，不能只在 payload 上打补丁。

**实施影响**

checkpoint 需要保存原文、补充轮次、结构化草稿、已确认实体引用、质量结果和待补字段；planner 需要做到幂等重算，不把旧 `WorkflowActionPlan` 当作事实来源。

**验收证据**

- 首轮质量 45，用户补充行动后变为 72：只有第二次通过后才允许写入；
- 补充把客户从 A 改为 B：不得写入 A；
- 补充改变时间：最终 payload 使用新时间；
- 重放同一 supplement 不产生重复活动。

---

### Q-06 本期是否恢复 `PAYMENT_RECORD`？

- **优先级：**P0
- **当前建议标签：**`PRODUCT_DECISION_REQUIRED` + `OUT_OF_SCOPE_CANDIDATE`
- **当前事实：**`CONFIRMED_REGRESSION`（相对于“统一 Workflow 应支持语义合同已声明的写入动作”这一合同）。

**当前证据**

- `AgentIntent` 和语义 Prompt 仍包含 `PAYMENT_RECORD`；
- Tool Registry 仍注册 `create_payment_plan`、`create_payment_record`；
- 旧 `payment_record_graph.py` 覆盖客户、合同/商机、回款计划选择、金额、日期、佣金归属人和最终确认；
- 旧 Action Planning Graph 仍有 `payment_record` 路由；
- 当前 `CRMWorkflowPlanner.plan()` 只有客户活动、客户/线索、联系人、发票抬头、部署信息、成员、商机和任务状态分支，没有 `PAYMENT_RECORD`。

**必须确认的问题**

1. `PAYMENT_RECORD` 是否纳入本次统一 Workflow？
2. 是否同时纳入 `CREATE_PAYMENT_PLAN`？
3. 是否需要完整恢复合同、商机、回款计划选择和佣金归属人路径？
4. 回款是否可以由跟进后的建议触发，还是必须用户明确输入？
5. 若本期不做，旧入口是否继续可用，还是应明确返回“不支持”？
6. API/前端是否已有独立回款录入入口可承接？

**推荐默认答案**

若统一 Workflow 宣称承接所有现有写入意图，则纳入 P0；若本期只做客户跟进，应把 payment 明确列为独立 Workflow/延期项，补充承接方和验收日期，不能让它静默落入 `WORKFLOW_ACTION_UNSUPPORTED`。

**实施影响**

需要决定是复用旧 payment domain graph 作为 native Workflow domain adapter，还是重写成 Planner command plan；两者都必须保留资源 revalidation、确认、授权和幂等。

**验收证据**

至少覆盖：唯一开放回款计划、多计划选择、无计划、金额/日期/佣金人缺失、取消、重复提交、权限拒绝和数据库最终记录。

---

## 4. P1：跟进写入后的客户业务闭环

### 已确认的本期范围（对应 Q-07）

本期跟进后的前台业务建议先只做到**商机**：识别到明确商机时，在 Agent 页面展示是否创建，并在用户同意后使用内嵌表单独立创建商机。

本期暂不处理回款、合同、回款计划、发票抬头、部署信息、License 等其他二级业务动作；这些动作不应因为语义信号被自动建议或执行，也不应阻塞跟进记录保存。

已确认：商机阶段推进属于本期商机范围，与商机创建一样，作为跟进完成后的独立二级动作处理。

### Q-07 跟进创建成功后是否必须生成业务建议？

- **优先级：**P1
- **当前建议标签：**`PRODUCT_DECISION_REQUIRED`

**旧流程证据**

旧 `BusinessContextGraphService` 在客户上下文读取后可调用 `AgentSuggestionGenerator`；建议支持商机、阶段、联系人、回款计划/记录、发票抬头、部署信息、License 等动作。旧 Action Planning Graph 会把建议添加到响应、挂到跟进 action 的 `next_task`，或转成第二步确认。

**当前 Workflow 证据**

当前生产装配只创建 `CRMWorkflowPlanner` 和 `CRMWorkflowEffectExecutor`；`get_customer_context` 和 `AgentSuggestionGenerator` 仍存在，但没有进入当前 Workflow Planner 的跟进创建路径。

**必须确认的问题**

1. 每条跟进是否都要生成建议，还是只有包含业务信号的跟进才生成？
2. 建议是否必须在活动写入成功后生成？
3. 质量不通过时是否绝对禁止建议？
4. 上下文为空或读取失败时，跟进是否仍可写入？
5. 建议只展示，还是可以形成可确认的二级 Workflow？
6. 建议最大数量和最低置信度是多少？

**推荐默认答案**

```text
质量通过 → 创建跟进成功 → 读取客户上下文 → 生成并过滤建议 → 下一轮唯一确认
```

建议不是跟进写入的必要条件；建议失败不回滚已成功写入的跟进，但必须产生独立错误/重试记录。质量失败时不生成建议。

**实施影响**

需要增加“活动成功后的建议阶段”或 durable follow-on job，并定义建议状态：`GENERATED`、`FILTERED`、`WAITING_USER`、`ACCEPTED`、`DISMISSED`、`FAILED`。

**验收证据**

质量失败无建议；质量通过且上下文成功时有建议；上下文失败时活动成功但建议标记失败且可重试；低置信度建议不出现在用户交互中但保留 trace。

---

### Q-08 跟进和二级动作是否允许同轮执行？

- **优先级：**P1
- **当前建议标签：**`CONFIRMED_REGRESSION`（旧交互规则已有明确方向）+ `PRODUCT_DECISION_REQUIRED`

**规则证据**

`interaction-policy.md` 明确：跟进是当前主产物时，先确认并创建跟进；商机创建、阶段推进等二级动作必须在跟进成功后进入第二个确认或补字段任务。

**必须确认的问题**

以下输入是否必须拆开？

```text
“记录这次跟进，并把商机推进到方案评估阶段。”
“记录跟进，同时创建一个回款计划。”
```

还需确认：

1. 第一轮是否只创建跟进？
2. 第二轮建议是否必须等活动成功事件，而不是仅依据模型输出？
3. 若用户明确同时授权两个动作，是否也必须拆为两个 confirmation？
4. 若第一步成功、第二步取消，如何展示最终状态？

**推荐默认答案**

不允许同轮执行两个独立业务副作用。第一轮仅完成质量门禁和跟进写入；第二轮以已成功活动和上下文为事实来源，单独提出一个最高优先级建议。

**实施影响**

不能用一个包含多个 command 的 `WorkflowActionPlan` 隐式执行跟进和二级动作，除非产品明确把它们定义成一个不可分割的原子业务事务；否则应拆成两个 Workflow/action identity。

**验收证据**

验证第一轮数据库只增加活动；商机/阶段/回款没有变化。第二轮用户确认后才产生对应二级副作用；取消第二轮不影响已成功的活动。

---

### Q-09 建议是否必须使用客户业务上下文？

- **优先级：**P1
- **当前建议标签：**`PRODUCT_DECISION_REQUIRED` + `API_PARITY_VERIFICATION_REQUIRED`

**旧流程证据**

旧业务上下文 graph 通过 `get_customer_context` 读取客户的商机、合同、回款计划、部署信息等，再将上下文传入 suggestion generator；suggestion guardrails 会依据上下文校验阶段、合同和回款计划引用。

**当前能力边界**

Query Agent 可以独立调用 `get_customer_context`，但当前写入 Workflow 不会自动复用 Query 结果；Workflow Planner 也没有 customer context reader 参数。

**必须确认的问题**

1. 客户上下文是不是建议生成的硬前置？
2. 哪些事实必须来自 CRM/API，哪些可以来自当前跟进文本？
3. 上下文读取失败时允许只写跟进吗？
4. 上下文部分缺失时是否生成部分建议？
5. 是否允许完全依据跟进文本提出建议？

**推荐默认答案**

上下文是建议的必要输入，但不是已通过质量门禁的跟进写入必要条件。强事实（客户、商机、合同、回款计划、阶段）必须来自服务端 API；跟进文本只能提供候选事实/业务信号。上下文失败则活动保留，建议不生成或进入可重试状态。

**实施影响**

需要确定使用 Query reader、独立 Workflow resource reader，还是 post-commit durable worker；必须沿用客户权限和服务端实体引用，不允许 planner 直接拼业务数据库查询。

**验收证据**

上下文中的商机状态与用户文本冲突时，以 API 为准；无权限对象不出现在建议 payload；上下文读取 5xx 时不阻止活动写入但不会生成未经证实的二级动作。

---

### Q-10 `business_signals` / `requested_actions` 的权威性是什么？

- **优先级：**P1
- **当前建议标签：**`PRODUCT_DECISION_REQUIRED`

**当前证据**

语义 schema 和 Prompt 仍输出业务信号、请求动作；旧 suggestion/action planning 会消费这些字段。但新 Planner 当前只消费活动内容、method、next_action、next_follow_time 和 intent confidence，没有消费这些字段。

**必须确认的问题**

1. 这些字段只是建议生成输入，还是能直接路由 Workflow？
2. 用户明确请求是否高于模型建议？
3. `requested_actions` 能否绕过建议阶段直接执行二级动作？
4. 模型识别出但未执行的动作是否保留？
5. 业务信号是否需要进入客户智能刷新或任务投影？

**推荐默认答案**

将二者视为候选证据，不是授权。最终能否执行必须由代码根据客户引用、权限、对象存在性、资源状态、置信度和单一交互规则重新裁决。用户明确请求可以提高候选优先级，但不能绕过确认/授权/资源 revalidation。

**实施影响**

需要保存“识别到但未执行”的候选动作及原因，避免用户误以为系统已经完成；建议 guardrail 需要明确过滤原因。

**验收证据**

模型输出 `CREATE_PAYMENT_RECORD` 但无开放回款计划时，不创建记录；用户明确要求推进阶段但目标商机不存在时，不凭文本创建隐式对象；被过滤动作在 trace 中有可解释原因。

---

### Q-11 跟进成功后的 next task projection 如何承接？

- **优先级：**P1
- **当前建议标签：**`PRODUCT_DECISION_REQUIRED` + `API_PARITY_VERIFICATION_REQUIRED`

**旧流程证据**

旧代码存在 `next_waiting_task_projection.py` 和 `business_rules.opportunity_next_task_from_suggestions()`；跟进 action 可以携带下一步任务候选，并通过稳定 key、父任务关系、用户/团队/session ownership 和幂等校验投影到任务系统。

**当前疑点**

当前活动 Tool 返回 `CustomerActivityDurableWorkReceipt`，durable work 明确承接 post-commit job 和客户智能 refresh；但 receipt 本身没有 next task projection 字段，需要确认 next task 是否有其他独立入口，还是已经在迁移中丢失。

**必须确认的问题**

1. 跟进建议是否自动成为 next task？
2. next task 是生成草稿、等待用户确认，还是直接创建可执行任务？
3. 一个跟进允许多个 child task 吗？
4. parent task、owner、session、activity 的关系如何保存？
5. 建议被拒绝是否记录 dismissal？
6. 幂等 key 是基于 activity、suggestion、workflow 还是 slot？

**推荐默认答案**

建议先作为下一轮唯一交互动作，不自动创建多个可执行 child task；用户确认后再通过稳定幂等 key 创建一个明确任务。所有未执行建议保留审计/trace，拒绝也要可区分于生成失败。

**实施影响**

需要决定 next task 属于 Workflow command、post-commit durable work，还是独立 suggestion projection；三者的 ownership、失败重试和用户确认语义不能混用。

**验收证据**

活动成功后只产生建议/待确认投影，不自动产生多个任务；确认后重放不重复建任务；取消或拒绝不改变活动事实；后台失败可重试并可在任务列表看到准确状态。

---

## 5. P2：数据契约、边界行为和迁移承接

### Q-12 `source_content` 保存原文还是规范化内容？

- **优先级：**P2
- **当前建议标签：**`PRODUCT_DECISION_REQUIRED` + `API_PARITY_VERIFICATION_REQUIRED`

**当前证据**

当前 `_plan_customer_activity()` 中：

```python
source_content = content
payload["source_content"] = content
payload["title"] = content
```

这里的 `content` 来自 semantic parser 的 `follow_up.content`，不一定等于用户原文。旧流程的 `parsed_from_semantic()` 同样会产生结构化/整理后的内容，但旧 state 仍保存原始 `content`。

**必须确认的问题**

1. `source_content` 是否必须逐字保存用户输入？
2. 是否同时保存 `normalized_content` / `title`？
3. 详情、时间线、报表分别展示哪一个？
4. 质量评估针对原文、规范化稿，还是两者？
5. 审计/回放需要哪个版本？
6. 模型改写是否必须用户确认？

**推荐默认答案**

```text
source_content = 用户原文
normalized_content/title = 结构化整理稿
```

事实以原文和服务端事实为准，模型不得未经用户确认编造、删除或替换关键事实。

**实施影响**

需要扩展 semantic/planner/payload 合同，并检查 CRM 活动 API 是否支持双字段；若旧 API 只有一个字段，需做兼容映射并明确展示规则。

**验收证据**

输入含口语、日期和否定表达时，活动可回放原文；规范化字段不得把“客户没有承诺”改写成“客户已承诺”；建议引用必须能追溯到原文和服务端上下文。

---

### Q-13 `method` 与 `activity_kind` 是否完全等价？

- **优先级：**P2
- **当前建议标签：**`API_PARITY_VERIFICATION_REQUIRED`

**当前证据**

当前 Workflow 只传：

```python
activity_kind = infer_activity_kind(method, content)
```

旧 semantic/API 合同仍使用 `method`；活动列表、详情、报表和查询是否依赖原 method，不能通过 Planner 单点判断。

**必须确认的问题**

1. CRM 活动存储和读取是否已迁移到 `activity_kind`？
2. `activity_kind` 是否可逆得到旧 method？
3. 未识别方式如何保存？
4. 是否需要同时写入 `method` 和 `activity_kind`？
5. 报表、筛选、历史数据是否有兼容要求？

**推荐默认答案**

在 API 和报表确认完全不依赖 `method` 前，同时保留兼容映射；无法映射时保存稳定的 `UNKNOWN`/原始值，而不是静默丢弃。

**验收证据**

通过 Agent 创建的活动在列表、详情、筛选、统计和旧数据对比中 method/activity_kind 语义一致。

---

### Q-14 创建客户/线索前重复检查是否被 API 完整承接？

- **优先级：**P2（若当前允许 Agent 直接创建，风险可升为 P0）
- **当前建议标签：**`API_PARITY_VERIFICATION_REQUIRED`

**旧流程证据**

旧 `CreationDuplicateGraphService` 在创建客户/线索前按名称、手机号及客户/线索交叉范围搜索，展示候选并让用户决定继续或取消。

**当前证据**

当前 Tool Registry 仍注册 `search_creation_duplicates`，其实现会按团队范围查询客户和线索、隐藏无权限对象并返回可见/隐藏数量；但当前 `CRMWorkflowPlanner` 没有 duplicate preflight。创建 API 也有名称冲突保护：`customers.py` 和 `leads.py` 在创建前调用 `_ensure_*_name_available()`，但这只能证明有请求级拒绝，不能证明有旧流程的主动提示和跨对象交互 parity。

**必须确认的问题**

1. API 是否只拒绝同名，还是同时检查手机号和客户/线索交叉冲突？
2. API 拒绝前是否已经创建任何副作用？
3. Agent 是否必须主动展示重复候选后再让用户决定？
4. 无权限的重复对象如何提示，是否保留“团队内存在匹配”的模糊提示？
5. 用户明确“仍然创建”是否允许绕过名称保护？
6. 批量导入和 Agent 单条创建是否共用同一规则？

**推荐默认答案**

创建客户/线索前主动 duplicate preflight 是交互能力，底层 API 的拒绝是数据安全能力，两者不可互相替代。除非产品明确关闭旧交互，否则应保留主动检查并在最终 command 执行前重新校验。

**实施影响**

需要为新 Workflow 增加 duplicate resource resolver 或 domain step；确认后 command 仍应接受 API 最终冲突保护。需要定义隐藏对象、候选选择、继续创建和取消的可恢复交互。

**验收证据**

同名客户、同手机号联系人、同名线索、客户/线索交叉冲突、无权限重复对象、重放和并发创建分别验证；数据库不能出现意外重复。

---

> **Q-14 针对商机的已确认修正：**商机重复检查不是“每次发现候选都让用户选择”。当已有商机与本次识别出的商机在关键事实和语义上高置信度匹配时，直接判定为已有商机，跳过创建，不打扰用户；如本次语义还包含推进阶段，则基于该已有商机继续评估阶段推进。只有匹配不确定、存在冲突或无法安全判断时，才请求用户介入。LLM 负责语义匹配，最终仍需以服务端实体和权限校验为准。

---

### Q-15 memory/current customer 是有意移除，还是迁移漏项？

- **优先级：**P2
- **当前建议标签：**`INTENTIONAL_DESIGN_CHANGE_CANDIDATE` + `API_PARITY_VERIFICATION_REQUIRED`

**当前证据**

旧流程先 `load_memory`，semantic parser 接受 memory，并可继承 `current_customer`。当前 Planner 固定以 `memory=None` 调用 parser；当前 Root context snapshot 主要保存 previous query、result set、active workflow、pending cases，不包含 `current_customer`。当前新 schema/资源绑定更强调显式、服务端签发的实体引用。

**设计证据**

`memory.md` 仍要求跨轮保存 `session_context.current_customer`，并规定“这个客户、继续”等承接表达优先使用当前客户；同时又要求运行时等待态不能从 session JSON 反向恢复，说明需要区分业务记忆和 pending runtime state。

**必须确认的问题**

1. current customer 是否应该恢复？
2. 如果恢复，权威来源是 checkpoint、Root context、session projection 还是 CRM API？
3. 是否只允许已签发 EntityRef，不允许模型自由声明 MEMORY？
4. 新客户显式出现时如何覆盖旧 current customer？
5. 刷新页面、跨 channel、跨 session 是否继承？

**已确认的产品原则（在推荐答案基础上的修正）**

保留当前客户，但它只能是**软上下文（candidate context）**，不能变成每轮写入的强制绑定，也不能由模型凭记忆直接决定。采用“低摩擦、风险自适应”的客户承接策略：

- 保存的是已由服务端确认过的 `EntityRef`，并附带来源、最近确认时间、会话/主题范围和权限上下文；不保存模型自由猜测的客户名称。
- 用户明确提到新客户时，新客户优先；如果新旧客户同时出现且无法判断用户意图，才请求澄清。
- 用户使用“这个客户”“继续跟进”“再补充一条”等承接表达时，默认把 current customer 作为候选，不立即打断用户。
- 只有在真正写入前，才进行最终客户和权限校验；校验通过且只有一个高置信度候选时直接继续，不重复询问。
- 如果候选不唯一、客户已失效/无权限、当前话题已切换，或本次操作风险较高且绑定证据不足，才使用轻量确认/选择组件，而不是每次都弹完整流程。
- 跟进补充时默认沿用已确认客户，但用户明确指定其他客户时允许切换，并从客户识别阶段重新规划受影响内容。
- current customer 需要有主题边界和合理的失效/降级策略，不能跨不相关主题、长期沉默或权限变化无限继承。
- pending interrupt 的恢复仍只能依赖 Workflow checkpoint；current customer 只用于语义承接，不能替代 pending runtime state。

这套策略的核心不是“永远相信 current customer”，也不是“每次都让用户确认”，而是：**确定时自动承接，不确定时才打扰，写入前始终由服务端重新验证。**

**实施影响**

需要扩展 `RootContextSnapshot` 或 Workflow runtime context，并更新 `resolution_source` 合同；应避免重新引入未经验证的 `MEMORY` 路径。

**验收证据**

“给这个客户加跟进”在有已验证 current customer 时成功绑定；显式新客户时不误绑旧客户；没有 current customer 时必须澄清；刷新/恢复行为和权限一致。

---

> **Q-16 已确认：**允许 Agent 在同一轮中先查询再继续操作。查询与写入仍是两个独立的操作原子，不合并成一个不可分割事务；查询结果明确且风险可控时不强制再次询问，只有结果不明确、存在冲突或确实需要用户决定时才中断。

### Q-16 Query 与 Workflow 是否允许同一轮读写混合？

- **优先级：**P2
- **当前建议标签：**`PRODUCT_DECISION_REQUIRED` + `INTENTIONAL_DESIGN_CHANGE_CANDIDATE`

**旧流程证据**

旧主图可在 semantic parse 后按场景执行 `run_agent_read_tool`，再构造响应；某些输入可以先读取任务/客户信息，再决定是否产生动作。

**当前架构证据**

新架构将 Query Agent 和 native Workflow 分开。Root 负责 route；Query executor 可根据客户引用调用 `get_customer_context`，但 Workflow Planner 不会自动读取 Query 结果。

**必须确认的问题**

1. “查一下这个客户，然后给他加一条跟进”是否支持同一轮？
2. 如果支持，组合编排应由 Root 负责，还是拆为两次用户交互？
3. Query 结果是否可以作为 Workflow 的权威输入？
4. 读操作失败是否阻止写操作？
5. 同轮是否允许多个 read tool 和一个 write command？

**推荐默认答案**

默认拆成两轮；如果必须支持组合场景，由 Root 显式编排：

```text
Query → 将服务端结果投影为受信任 EntityRef/Context → Workflow
```

不能让 Workflow Planner 隐式执行任意读写，也不能让 LLM 把文本查询结果当成授权绑定。

**实施影响**

可能需要 Root continuation contract、查询结果到 Workflow 的 typed binding，以及跨阶段权限/过期 revalidation。

**验收证据**

组合输入要么明确被拆分并提示用户，要么按 Root contract 先返回查询再等待后续写入；不得一次请求产生未确认的读写混合副作用。

---

> **Q-17 已确认：**现有跟进保存后的后台 post-commit 体验是好的，本期必须保持其行为和用户体验不退化。跟进保存成功后，后台继续自动投影/更新跟进待办、刷新客户智能并在失败时重试；这些后台处理不阻塞、不回滚主跟进记录，也不要求用户额外参与。新接入的跟进质量门禁、商机建议和商机操作不得破坏这条链路。

### Q-17 durable work 是否完整承接旧 post-write 链路？

- **优先级：**P2
- **当前建议标签：**`API_PARITY_VERIFICATION_REQUIRED`

**当前事实**

活动写入返回 `CustomerActivityDurableWorkReceipt`，包含：

```text
activity_id
post_commit_job_public_id
customer_intelligence_request_id
```

`AgentDurableWorkBinder` 会绑定 post-commit operation projection、活动来源和 customer intelligence refresh；post-commit projector 负责将后台任务状态投影到 Agent operation。客户智能刷新服务也有 durable registration、kick、retry/recovery 机制。

**不能直接推导的部分**

这证明了新的承载机制存在，但不能自动证明旧 `post_write_effects` 的每一项都已承接，尤其是：

- next task projection；
- 建议状态和二级动作；
- 活动质量结果；
- 旧任务/活动关联；
- Agent turn 是否能看到后台最终结果。

**必须确认的问题**

1. 旧 post-write effects 的完整清单是什么？
2. 每一项由 durable work、customer intelligence、Agent UI operation 还是其他 worker 承接？
3. 失败后活动是否保留？后台是否可重试？
4. 重试和并发是否幂等？
5. durable work 完成是否会更新会话/消息投影？
6. next task projection 是否属于本链路？

**推荐默认答案**

把 durable receipt 视为基础承载，不默认视为完整 parity。建立 old effect → new worker/operation 的逐项映射，并用真实数据库和后台恢复回放证明。

**实施影响**

需要补充 durable work contract、状态机、reconciliation 和回放测试；若建议/任务不属于 post-commit，应单独创建明确的 durable work 类型。

**验收证据**

活动提交成功后模拟 worker 超时、进程重启、重复领取、部分完成和最终重试；验证活动不重复、operation 最终可见、customer intelligence 可恢复、任务/建议状态不丢失。

---

### Q-18 质量结果的持久化范围是什么？

- **优先级：**P2
- **当前建议标签：**`PRODUCT_DECISION_REQUIRED`

**必须确认的问题**

1. 质量分是否写入 CRM activity？
2. 是否只写 Agent trace/checkpoint？
3. 是否用于 customer intelligence？
4. 补充前后是否都保留？
5. 是否需要按六大原则做运营报表？
6. 如何处理模型/fallback/人工修改后的版本关系？

**推荐默认答案**

至少保留 checkpoint + trace；不把质量分伪装成业务事实字段。只有明确需要质量报表时，才新增正式质量记录表，且保留 evaluator version、model source、fallback reason 和评估时间。

**实施影响**

需要版本化质量 schema 和隐私/保留期限策略；前端可见的质量分与内部运营分数应分别定义。

**验收证据**

同一跟进多轮补充时能查到每轮结果；活动详情不出现未经产品批准的内部模型字段；trace 可以解释最终是否因质量门禁被阻止。

---

### Q-19 quality/context/suggestion 失败采用 fail-open 还是 fail-closed？

- **优先级：**P2
- **当前建议标签：**`PRODUCT_DECISION_REQUIRED`

**建议默认策略**

| 阶段 | 推荐策略 | 原因 |
|---|---|---|
| semantic parse | fail-closed，不写入 | 无法确定动作和事实 |
| quality evaluator | fail-closed，不写入 | 无法证明跟进达到最低质量 |
| customer resolution | fail-closed，不写入 | 无法建立权威客户绑定 |
| customer context | 活动可写，建议不生成 | 上下文是建议输入，不应阻止已合格事实记录 |
| suggestion generation | 活动不回滚，建议标记失败并可重试 | 二级建议不是主活动事实 |
| post-commit refresh | 活动保留，后台重试 | 已提交事实不能因异步刷新失败回滚 |
| duplicate preflight | 取决于最终 API 合同；推荐 fail-closed | 避免未知重复写入 |

**必须确认的问题**

- 是否接受上述默认策略？
- “质量服务暂时不可用”是否允许人工确认绕过？
- 上下文/建议失败是否要在用户最终回复中显式提示？
- 后台失败重试次数、告警和人工补偿入口是什么？

**实施影响和验收**

需要在 `WorkflowEffectResult`、durable operation 和 trace 中区分主动作失败、二级建议失败、后台刷新失败，不能都投影为 `INTERNAL_ERROR`。

---

## 6. P3：运行时、审计和用户可见性

### Q-20 progress 是否恢复领域步骤？

- **优先级：**P3
- **当前建议标签：**`PRODUCT_DECISION_REQUIRED`

**当前 Workflow 进度**

`workflow/progress.py` 当前只有通用步骤：

```text
理解业务操作
接收补充信息
生成执行计划
等待确认
执行 CRM 操作
整理执行结果
```

**旧/设计领域步骤**

旧流程和设计规则还表达了：

```text
加载会话记忆
语义理解
检查重复
搜索客户
评估跟进质量
加载客户上下文
生成业务建议
投影下一步任务
后台处理
```

**必须确认的问题**

1. 哪些步骤对用户可见，哪些只进内部 trace？
2. 质量分是否展示？
3. 低质量时是否只展示补充问题而隐藏其他步骤？
4. durable work 是否显示“后台对账中/已完成/重试中”？
5. Query 和 Workflow 是否共用一套 UI process contract？

**推荐默认答案**

用户界面显示简化业务步骤，内部 trace 保留完整领域步骤；质量失败只展示唯一补充问题；后台任务显示明确的异步状态，不伪装为同步完成。

**验收证据**

前端 Agent UI、IM 和历史消息投影都能正确表达：等待质量补充、等待客户选择、等待确认、主活动完成、后台对账中、后台失败可重试。

---

### Q-21 trace/observability 是否要求恢复旧领域事件？

- **优先级：**P3
- **当前建议标签：**`PRODUCT_DECISION_REQUIRED`

**旧流程事件**

旧流程有 semantic trace、quality trace、business context trace、suggestion trace、tool trace、fallback metadata 和 failure events。

**当前问题**

native Workflow 目前可以产出结构化结果、checkpoint 和通用 progress，但 Planner 不会产生质量/建议领域事件。若只看最终“已记录跟进”，无法知道是否执行了质量门禁、为何没有建议、为何某候选动作被过滤。

**必须确认的问题**

1. 是否要求旧领域事件与新事件一一 parity，还是只需业务结果 parity？
2. evaluator/parser 的模型来源、fallback 原因、评分是否对用户可见？
3. suggestion 被过滤的原因是否进 trace？
4. 所有失败是否必须有 trace_id？
5. 是否接入 LangSmith 或其他统一追踪系统？

**推荐默认答案**

不要求事件名称逐字兼容，但要求关键决策可审计：

```text
semantic parsed
quality evaluated / blocked / passed
customer resolved / candidates
context loaded / failed
suggestions generated / filtered / awaiting decision
command authorized / executed
post-commit completed / retried / failed
```

**验收证据**

给定任一活动 ID 或 workflow ID，可以回放其质量判定、客户绑定、command、后台任务和最终状态；错误能关联 trace_id。

---

### Q-22 checkpoint 是否保存所有可恢复的领域中间结果？

- **优先级：**P3
- **当前建议标签：**`API_PARITY_VERIFICATION_REQUIRED` + `PRODUCT_DECISION_REQUIRED`

**设计规则**

`memory.md` 要求 checkpoint 保存当前客户、候选对象、草稿 payload、缺失字段、已补字段、guardrail 结果、tool request/result 和事件摘要，并禁止保存不可序列化运行时对象。

**必须确认的新跟进字段**

```text
source_content
supplement_rounds
semantic_result
quality_result / metadata
missing_aspects / supplement_question
customer candidates / selected entity ref
normalized follow-up payload
business context
suggestion candidates / filtering reasons
next task projection
pending interaction
post-commit receipt / operation reference
```

**必须确认的问题**

1. 哪些字段是 resume 必需，哪些只需 trace？
2. 用户补充前后的质量结果是否进入 checkpoint？
3. business context/suggestion 是否允许进入 checkpoint，还是只保存引用？
4. checkpoint 中的 payload 是否可作为最终执行事实？
5. checkpoint 过期、清理和迁移策略是什么？

**推荐默认答案**

所有会影响 resume/replay/audit 的 JSON-safe 领域状态进入 checkpoint；数据库 session、HTTP client、模型 client 和权限实现不进入。最终执行必须基于 checkpoint 中已确认的 plan，但 plan 依赖的资源在执行前仍需 API revalidation。

**验收证据**

重启服务、刷新页面、切换 channel 后能够恢复唯一 pending action；不能从 session JSON 猜测旧任务；重复 resume 不重复写入。

---

## 7. 需要额外确认的“其他遗漏面”

以下不是 Q-01～Q-22 的重复，而是 parity 收口时必须补充核对的横切能力。如果不单列，容易在恢复主流程时再次漏掉。

### Q-23 一个用户输入是否允许生成多个 CRM command？

- **优先级：**P1
- **标签：**`PRODUCT_DECISION_REQUIRED`

当前 `WorkflowActionPlan` 支持多个有序 command，并支持 command binding；这对“创建客户后绑定首次跟进”是必要的，但也可能把“跟进 + 商机 + 回款”误打包成一个确认动作。

必须确认：

- 哪些 command 组合是一个原子业务动作；
- 哪些必须拆成多轮确认；
- 部分成功如何补偿；
- 一个 action_id 下的多个副作用如何展示和审计。

推荐：只有有明确业务原子性和同一授权边界的组合才允许多 command；二级建议默认拆分。

### Q-24 自动执行阈值是否只看 intent confidence？

- **优先级：**P0
- **标签：**`CONFIRMED_REGRESSION`

当前活动自动执行条件是 `intent_confidence >= 0.85`，而 Workflow contract 还要求低风险。需要确认自动执行是否同时要求：

```text
quality passed
customer uniquely bound
next-step policy passed
payload completeness passed
no duplicate risk
low-risk action
intent confidence >= 0.85
```

推荐不允许 intent confidence 单独授权写入；跟进质量和行动闭环必须是独立门禁。

### Q-25 客户/线索创建后的首次跟进是否也要经过质量门禁？

- **优先级：**P1
- **标签：**`PRODUCT_DECISION_REQUIRED`

当前 `_plan_customer()` / `_plan_lead()` 可以在创建对象时带首次跟进内容；需要确认这类“创建客户/线索 + 首次跟进”是否同样适用六大质量原则，还是只要求内容非空。若适用，需规定：

- 质量失败时是否连客户/线索也不能创建；
- 是否允许先创建主体、后补跟进；
- 多 command 原子性如何处理。

### Q-26 客户智能刷新与 Agent 建议是否有重复计算/时序冲突？

- **优先级：**P2
- **标签：**`API_PARITY_VERIFICATION_REQUIRED`

活动提交后既有 customer intelligence refresh，又可能恢复同步/异步建议生成。需要确认：

- 建议使用写入前上下文还是刷新后的上下文；
- customer intelligence 还未完成时是否允许建议；
- 两个后台任务是否会重复读取/覆盖相同 projection；
- 失败重试是否保持相同版本和幂等 key。

推荐：建议以活动提交成功为触发点，但强事实读取必须明确版本；如果依赖刷新后的客户档案，应等待对应 durable completion 或显示“建议稍后生成”。

### Q-27 权限、实体引用和执行前 revalidation 是否对所有恢复动作一致？

- **优先级：**P1
- **标签：**`API_PARITY_VERIFICATION_REQUIRED`

当前 Workflow 对客户绑定和商机阶段有资源 resolver/revalidation，但恢复质量补充、建议确认、payment、next task 等路径是否都使用相同授权范围仍需核对。必须验证：

- 选中的客户引用过期/被删除；
- 用户权限在等待期间变化；
- 商机阶段在确认前发生变化；
- pending action 被另一个请求抢先执行；
- 用户、团队、session ownership 不一致。

推荐：所有等待后恢复的写入 command 都必须基于 checkpoint 引用并执行最新服务端 revalidation。

### Q-28 取消、拒绝、切换和超时后的状态是否完整？

- **优先级：**P2
- **标签：**`PRODUCT_DECISION_REQUIRED` + `API_PARITY_VERIFICATION_REQUIRED`

除“确认/取消”外，质量补充和建议还会引入：

```text
supplement_cancelled
suggestion_dismissed
workflow_switched
pending_expired
resource_stale
retry_exhausted
```

需要确认这些状态是否：

- 保留在 checkpoint；
- 投影到 Agent task/message；
- 能否重新发起而不重复写入；
- 是否影响当前客户记忆和后续建议。

---

## 8. 统一的待确认清单

| 编号 | 主题 | 优先级 | 当前标签 | 是否阻塞实现 | 推荐默认 |
|---|---|---:|---|---|---|
| Q-01 | 质量评估顺序 | P0 | CONFIRMED_IMPLEMENTATION | 否 | 客户绑定后、写入前评分；质量不通过只问一个补充问题 |
| Q-02 | next_action 必填规则 | P0 | PRODUCT_DECISION_REQUIRED | 是 | 默认要求闭环；显式“暂无下一步”需有原因/复查条件 |
| Q-03 | 60 分阈值和质量字段 | P0 | REGRESSION / PRODUCT_DECISION_REQUIRED | 部分 | `<60` 阻塞，异常 fail-closed，结果进 checkpoint/trace |
| Q-04 | 低质量交互优先级 | P0 | CONFIRMED_REGRESSION | 是 | 只问一个质量问题 |
| Q-05 | 补充后的全量重规划 | P0 | CONFIRMED_REGRESSION / PRODUCT_DECISION_REQUIRED | 是 | 重新 parse + quality + resolution + context |
| Q-06 | PAYMENT_RECORD 范围 | P0 | PRODUCT_DECISION_REQUIRED / OUT_OF_SCOPE | 是 | 纳入统一 Workflow，或明确独立承接方 |
| Q-07 | 跟进后是否生成建议 | P1 | PRODUCT_DECISION_REQUIRED | 是 | 活动成功后生成，质量失败不生成 |
| Q-08 | 二级动作是否同轮执行 | P1 | REGRESSION / PRODUCT_DECISION_REQUIRED | 是 | 跟进和二级动作拆两轮 |
| Q-09 | 上下文是否为建议硬前置 | P1 | PRODUCT_DECISION_REQUIRED / API VERIFY | 是 | 是建议必要输入，不阻止主活动 |
| Q-10 | business_signals/requested_actions 权威性 | P1 | PRODUCT_DECISION_REQUIRED | 是 | 只作候选证据，不能直接授权 |
| Q-11 | next task projection | P1 | PRODUCT_DECISION_REQUIRED / API VERIFY | 是 | 建议先确认，单任务、稳定幂等 |
| Q-12 | source_content 原文合同 | P2 | PRODUCT_DECISION_REQUIRED / API VERIFY | 否（但阻塞数据收口） | 原文与规范化稿分离 |
| Q-13 | method/activity_kind 兼容 | P2 | API_PARITY_VERIFICATION_REQUIRED | 否 | API 证明前保留兼容映射 |
| Q-14 | 创建前重复检查 | P2/P0 | API_PARITY_VERIFICATION_REQUIRED | 创建能力前是 | 主动检查 + API 最终保护 |
| Q-15 | memory/current customer | P2 | DESIGN CHANGE / API VERIFY | 是跨轮体验 | 恢复受信任 current customer，不恢复自由猜测 |
| Q-16 | Query/Workflow 同轮读写 | P2 | PRODUCT_DECISION_REQUIRED / DESIGN CHANGE | 是组合场景 | 默认拆两轮，组合由 Root 显式编排 |
| Q-17 | durable post-write parity | P2 | API_PARITY_VERIFICATION_REQUIRED | 是发布前 | 建立旧 effects 到新 worker 的逐项映射 |
| Q-18 | 质量结果持久化 | P2 | PRODUCT_DECISION_REQUIRED | 否/运营场景是 | checkpoint + trace，正式报表另建模型 |
| Q-19 | 失败开关策略 | P2 | PRODUCT_DECISION_REQUIRED | 是 | 主事实/建议/后台分别处理 |
| Q-20 | progress 领域步骤 | P3 | PRODUCT_DECISION_REQUIRED | 否 | UI 简化，trace 完整 |
| Q-21 | trace 事件 parity | P3 | PRODUCT_DECISION_REQUIRED | 发布前建议 | 事件名可变，关键决策必须可审计 |
| Q-22 | checkpoint 中间结果 | P3 | API VERIFY / PRODUCT_DECISION_REQUIRED | 恢复能力是 | 保存所有可恢复 JSON-safe 领域状态 |
| Q-23 | 多 command 原子性 | P1 | PRODUCT_DECISION_REQUIRED | 是 | 只允许明确原子组合 |
| Q-24 | 自动执行综合门禁 | P0 | CONFIRMED_REGRESSION | 是 | intent confidence 不能单独授权 |
| Q-25 | 首次跟进质量 | P1 | PRODUCT_DECISION_REQUIRED | 是创建组合时 | 明确是否与普通跟进同一门禁 |
| Q-26 | 智能刷新/建议时序 | P2 | API_PARITY_VERIFICATION_REQUIRED | 建议接入前 | 明确版本、触发点和幂等 |
| Q-27 | 恢复动作权限 revalidation | P1 | API_PARITY_VERIFICATION_REQUIRED | 是 | 所有 resume command 统一校验 |
| Q-28 | 取消/拒绝/切换/超时状态 | P2 | PRODUCT_DECISION_REQUIRED / API VERIFY | 是交互收口 | 每种终态可恢复、可审计、不可重复写 |

---

## 9. 推荐确认顺序

### 第一批：先锁住“会不会错误写入”

必须先确定：

1. Q-01 质量评估顺序；
2. Q-02 下一步行动规则；
3. Q-03 阈值与 evaluator 失败策略；
4. Q-04 单一交互优先级；
5. Q-05 补充后的重新规划；
6. Q-24 自动执行综合门禁；
7. Q-27 恢复后的权限和资源 revalidation。

这一批未确定前，不应把当前高置信度自动创建行为继续扩展到更多写入动作。

### 第二批：锁住“跟进是否形成业务闭环”

1. Q-07 跟进后建议；
2. Q-08 二级动作拆分；
3. Q-09 客户上下文来源；
4. Q-10 业务信号/请求动作的权威性；
5. Q-11 next task projection；
6. Q-23 多 command 原子性；
7. Q-26 智能刷新和建议时序。

### 第三批：锁住“其他写入能力和 API parity”

1. Q-06 PAYMENT_RECORD 范围；
2. Q-14 创建前重复检查；
3. Q-16 Query/Workflow 组合；
4. Q-17 durable post-write parity；
5. Q-25 首次跟进质量。

### 第四批：锁住“数据、恢复、审计和前端”

1. Q-12 source_content；
2. Q-13 method/activity_kind；
3. Q-15 current customer/memory；
4. Q-18 质量持久化；
5. Q-19 失败策略；
6. Q-20 progress；
7. Q-21 trace；
8. Q-22 checkpoint；
9. Q-28 取消/拒绝/切换/超时。

---

## 10. 实施前需要补齐的证据包

在进入实现前，建议形成以下最小证据包：

### 10.1 代码路径证据

- 当前 Root 生产装配：`CRM-Server/app/services/agent/orchestrator/runtime.py`
- Root 路由和 context：`CRM-Server/app/services/agent/orchestrator/graph.py`、`context.py`
- 新 Planner：`CRM-Server/app/services/agent/workflow/planning.py`
- Workflow graph/executor/contracts/progress：`CRM-Server/app/services/agent/workflow/`
- 当前 customer activity tool、durable receipt 和 post-commit：
  - `CRM-Server/app/services/agent/tools/service.py`
  - `CRM-Server/app/services/agent/durable_work.py`
  - `CRM-Server/app/services/agent/durable_work_contracts.py`
  - `CRM-Server/app/services/customer_activity_post_commit_job_service.py`
  - `CRM-Server/app/services/customer_activity_post_commit_operation_projector.py`
  - `CRM-Server/app/services/customer_intelligence_refresh_service.py`
- 当前 duplicate Tool 和 API：
  - `CRM-Server/app/services/agent/tools/service.py`
  - `CRM-Server/app/services/agent/tool_registry.py`
  - `CRM-Server/app/api/customers.py`
  - `CRM-Server/app/api/leads.py`

### 10.2 旧流程对照证据

- `5641fff^:CRM-Server/app/services/agent/graph.py`
- `5641fff^:CRM-Server/app/services/agent/follow_up_quality_graph.py`
- `5641fff^:CRM-Server/app/services/agent/business_context_graph.py`
- `5641fff^:CRM-Server/app/services/agent/action_planning_graph.py`
- `5641fff^:CRM-Server/app/services/agent/creation_duplicates_graph.py`
- `5641fff^:CRM-Server/app/services/agent/payment_record_graph.py`
- `5641fff^:CRM-Server/app/services/agent/post_write_effects.py`
- `5641fff^:CRM-Server/app/services/agent/next_waiting_task_projection.py`

### 10.3 公共 API/数据库验收证据

至少补充以下场景，并保存请求、事件、消息投影和数据库副作用：

1. 低质量跟进；
2. 缺少下一步行动；
3. 质量补充后通过；
4. 质量补充后仍不通过；
5. 客户不唯一 + 低质量；
6. 高置信度无行动，确认不得自动写入；
7. 跟进写入成功后的上下文和建议；
8. 建议确认/拒绝/重放；
9. payment record 入口；
10. 客户/线索重复创建；
11. 页面刷新后的 pending 恢复；
12. 权限变化后的 resume；
13. durable worker 失败、重试、重启和幂等。

已有验收报告已指出：2026-08-24 的写入型 Workflow 公共 API 尚未完成，直接跟进写入、显式客户绑定、字段修改、Workflow 恢复等仍有 P0/PARTIAL；2026-08-27 报告只覆盖 Query，不代表写入型 Workflow parity 已完成。

---

## 11. 当前阶段的明确结论

1. **已确认不是只漏了跟进质量节点。**至少还涉及下一步行动门禁、质量补充重规划、客户上下文、业务建议、二级动作、next task projection、payment record 入口、重复检查、memory/current customer、读写组合、durable post-write、progress/trace/checkpoint 等。
2. **其中 Q-01～Q-05、Q-24 是直接影响跟进写入安全的 P0。**这些事项应先形成产品确认和自动化验收，再改 Planner。
3. **Q-06 是明确的生产路径能力缺口，但是否本期恢复是产品范围决策。**不能把 Tool Registry 中仍存在 `create_payment_record` 当作已迁移。
4. **Q-07～Q-11 是决定 CRM 是否从“记一笔”恢复到“形成业务闭环”的关键。**只恢复质量评估而不接回建议和任务投影，仍然不是旧流程 parity。
5. **Q-12～Q-22 不能用“代码里没有”直接判定。**其中多项可能是架构设计变化或由 API/durable worker 承接，必须通过合同和公共验收确认。
6. **暂不修改业务代码。**下一步应先对第一批和第二批逐项确认；确认后再将结果转成实现 tickets 和测试场景，而不是整体恢复旧 `graph.py`。
