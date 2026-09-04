# P2-PKG-03 页面动作收尾与下一步导航一致性 TRD

- **文档类型**：Technical Requirements Document（技术需求文档）
- **所属改造包**：P2-PKG-03 页面动作收尾与下一步导航一致性
- **优先级**：P2
- **版本**：v0.2
- **日期**：2026-09-04
- **适用系统**：CRMWolf 非 Agent / AI 自动化业务链路
- **排除范围**：Agent / AI 自动化链路；P1 高风险操作确认、状态反馈、错误恢复、DataTable 固定高度和操作列可发现性本身；审批中心成组审批能力
- **关联 PRD**：P2-PKG-03 页面动作收尾与下一步导航一致性 PRD
- **分析基线**：当前 `CRM-Client` 仓库静态代码核查；上线前需通过接口联调、异常注入和关键任务验收

> 本 TRD 解决的是“动作已经完成，但用户无法稳定判断对象最终状态和合理下一步”的收尾一致性问题。技术方案不改变业务动作、审批链、状态机、API 契约或页面主流程；不把普通保存统一改造成二次弹窗，也不以全局复杂流程编排替代现有页面逻辑。

## 1. 技术结论

### 1.1 结论

系统存在优化空间，但不需要推倒重来。当前主要问题不是“没有成功提示”，而是各页面对以下三件事的表达不一致：

1. **动作结果**：请求是否成功、失败，还是结果暂时未知；
2. **对象结果**：客户、追踪任务、商机、合同、回款计划或回款记录最终处于什么状态；
3. **下一步**：用户是否需要继续提交审批、查看对象、登记下一笔、处理待确认事项，或只是继续浏览当前列表。

建议采用“**页面级结果契约 + 统一收尾策略 + 局部下一步入口**”的方案：

- 低风险保存：Toast + 原上下文保留 + 列表/详情同步；
- 状态推进：Toast + 对象状态立即更新 + 明确可执行下一步；
- 审批提交：Toast + 审批状态或业务状态刷新，不强制跳转审批中心；
- 回款登记：保留现有金额、剩余金额、计划状态摘要及 `PaymentNextStepDialog`；
- 删除：Toast + 从当前列表移除 + 清理详情选择；
- 结果未知：沿用 P1 的查询、重试、人工确认语义，禁止直接显示“成功”；
- 返回与焦点：恢复到原列表上下文或原触发控件，不新增无必要的跳转；审批中心所有审批动作保持逐条处理。

### 1.2 不能做的“过度优化”

以下方案不纳入本 TRD：

- 每次保存成功后都弹出“下一步”弹窗；
- 所有操作成功后都强制跳转详情页或审批中心；
- 新增全局工作流引擎、全局任务队列或新的业务对象；
- 修改后端状态机、审批链、接口字段含义；
- 将已经实现的回款登记结果摘要重新开发一遍；
- 用一套统一文案掩盖不同业务对象的真实状态；
- 通过延迟刷新制造“看起来成功”的乐观状态，而没有最终读取确认。

## 2. PRD 到系统现状映射

### 2.1 客户信息保存

**当前实现：**

- `Customers.vue` 通过 `CustomerFormDialog` 创建或编辑客户；
- `CustomerFormDialog.vue` 成功后自行显示“客户创建成功/客户更新成功”，关闭 Dialog，再触发无 payload 的 `success` 事件；
- 父页面 `handleCustomerFormSuccess` 关闭状态并重新获取客户列表；
- 编辑流程已先获取详情再打开弹窗，避免从 loading 状态跳到完整表单的视觉闪烁；
- 客户详情 Sheet 通过 `@refresh` 触发列表刷新。

**技术缺口：**

- `success` 不携带客户 ID、操作类型或更新后的对象，父页面只能全量刷新；
- Toast 说明“保存成功”，但不保证当前列表行、详情 Sheet 和操作权限状态已经同步；
- 新建客户后的“新建商机”是业务上可能存在的下一步，但当前没有统一定义是否展示入口；
- Dialog 内部和父页面共同参与关闭，职责虽可工作，但成功后上下文恢复规则没有形成可复用契约。

**本期处理：**

- 保留 Dialog 内 Toast 和关闭行为，新增可选的结构化 success payload；
- 父页面按对象 ID执行“局部更新优先、刷新兜底”；
- 若当前来源是客户详情 Sheet，优先保持 Sheet 和当前分区，不因普通保存强制跳转；
- 新建客户后的下一步只作为页面级可选入口，不默认新增弹窗。

### 2.2 客户跟进完成

**当前实现：**

- `CustomerTracking.vue` 的 `transitionTask(task, action)` 通过 `followUpTaskApi.transition` 完成或关闭任务；
- 从详情 Sheet 操作时会清空选中任务并关闭 Sheet；列表操作时更新选中任务；
- 成功后 Toast + `fetchTasks()`；
- `FollowUpFormDialog.vue` 支持“提交”与“提交并完成追踪”，后者通过 `createActivityAndCompleteTracking` 完成原子业务动作，并以任务 ID作为 success payload；
- 待确认流程通过 `followUpConfirmation` Store/API 处理，已有“保持待处理、关闭、延期、确认完成”分支以及结果未知后的刷新基础。

**技术缺口：**

- 同一类“完成”动作因入口不同而有不同的上下文结果：详情入口关闭 Sheet，列表入口保留选中任务；
- Toast“已完成”没有稳定表达任务状态、完成时间或下一步是否需要新增跟进；
- 追踪详情、列表行、客户关联活动之间没有统一的同步顺序和失败降级说明；
- P1 已覆盖待确认和结果未知基础，本期不能重复制造另一套确认流程。

**本期处理：**

- 完成/关闭成功后，先更新任务读模型，再根据入口决定保留或关闭详情；
- 详情入口默认关闭已终结任务，但保留“回到列表原行”的焦点和筛选/分页上下文；如任务仍需后续动作，则在列表行或客户关联区提供轻量入口；
- 列表入口默认保留列表上下文，更新当前行状态，不强制打开详情；
- “提交并完成追踪”沿用现有原子 API 和 task ID 回传，不拆成两个独立请求。

### 2.3 商机状态推进

**当前实现：**

- `Opportunities.vue` 通过 `procurementApi.getOpportunityProcurementStages`读取采购阶段；
- 找到起始阶段或下一阶段后，先走确认，再调用 `moveOpportunityStage`；
- 成功后显示“起始阶段已设置/阶段已推进”，刷新列表；
- 商机新建、编辑、删除、赢单、输单等操作也主要采用关闭 Dialog + Toast + 刷新列表；
- 商机详情通过 Sheet 和路由 query 打开。

**技术缺口：**

- 阶段推进成功提示没有携带目标阶段、赢率、审批状态或下一可执行动作；
- 详情 Sheet 打开时的对象和列表刷新的对象没有统一 ID 级同步；
- “已是最终阶段”“未配置采购阶段”等业务结果使用警告提示，但没有区分“不能继续推进”和“系统配置缺失”。

**本期处理：**

- 推进成功结果至少包含商机 ID、目标阶段名称、目标阶段类型/状态（若 API 已提供）和下一动作类型；
- 列表行显示最新阶段和操作可用性；详情打开时触发局部详情刷新或使用响应对象更新；
- 不新增阶段状态机，不改变推进确认；
- 已是最终阶段继续使用非错误提示，并明确“当前无需继续推进”；配置缺失仍按业务/系统配置错误处理。

### 2.4 合同创建、保存和提交审批

**当前实现：**

- `ContractFormDialog.vue` 负责合同创建/编辑，成功后 Toast、关闭 Dialog、触发无 payload 的 `success`；
- `Contracts.vue` 创建/编辑成功后刷新列表；
- `handleSubmitApproval` 调用 `approvalGenericApi.submitApproval('CONTRACT', record.id)`，成功后 Toast“合同已提交审批”并刷新；
- 合同有详情 Sheet，列表中的合同状态由接口数据驱动。

**技术缺口：**

- 创建、编辑和提交审批三种结果的反馈结构不同；
- 提交审批后没有明确显示“审批中/已直接通过/待谁处理”等 API 已知状态；
- 列表刷新完成前，用户可能看到旧状态并再次点击提交；
- Dialog success 无对象信息，无法精确同步已修改合同的详情 Sheet。

**本期处理：**

- 提交审批成功后以响应或刷新后的合同对象为准展示状态，不通过文案猜测状态；
- 对审批状态为“提交成功但状态读取失败”的场景，显示“已提交，请刷新确认”而不是宣称最终状态；
- 提交按钮使用行级 pending key 防重复；
- 合同创建/编辑 success payload 至少携带合同 ID、操作类型和是否需要刷新详情；
- 不新增“提交审批后强制进入审批中心”的流程。

### 2.5 回款计划和回款登记

**当前实现：**

- `PaymentPlans.vue` 的 `handleRegisterSubmit` 已具备较完整的收尾逻辑：幂等 key、结果未知恢复查询、更新后的计划详情、登记金额、剩余金额、计划状态、关闭登记 Dialog、清理选择并刷新列表；
- `PaymentNextStepDialog.vue` 已提供“立即提交审批、稍后提交、查看详情”；
- `PaymentPlanFormDialog.vue` 创建/编辑成功后 Toast + 关闭 + `success`；
- `PaymentRecords.vue` 详情 Sheet、编辑 Dialog、重新提交审批、结果未知和列表同步已经存在，但页面状态组合较复杂。

**技术结论：**

本期不重复建设回款登记结果摘要，也不替换 `PaymentNextStepDialog.vue`。其现有实现作为本期其他财务动作的参考样板。

**本期处理：**

- 抽象“结果摘要 + 后续动作”所需的最小类型和页面适配，不强行把所有回款逻辑搬到全局组件；
- 回款计划创建/更新沿用低风险保存策略；
- 回款记录编辑/重新提交审批沿用当前详情 Sheet 与列表同步机制，补充统一的对象结果刷新顺序；
- 删除、审批提交等常规操作只补齐状态同步和下一步文案，不新增第二层确认。

### 2.6 发票与审批中心

**当前实现：**

- `ApprovalCenter.vue` 已具备快速同意、驳回、催办、单条结果反馈、409 并发冲突刷新，以及发票/合同详情 Sheet 刷新；
- 发票相关保存和审批状态由现有页面/API承担。

**技术缺口：**

- 审批完成后，审批对象的业务状态和审批中心状态不总是以同一节奏刷新；
- 单条审批结果需要保持对象级可追踪，不应只显示无法定位对象的通用 Toast；
- 不能把 P1 已有的审批确认、错误、并发冲突处理再次立项。

**本期处理：**

- 审批中心仅保留逐条审批：每条审批分别确认、分别提交、分别反馈成功或失败，并保留单条并发冲突后的刷新与重试语义；
- 单条审批成功后刷新审批任务和业务对象读模型；
- 详情 Sheet 若仍打开，刷新当前对象；若对象已离开当前筛选结果，关闭或显示对象已更新提示，由页面策略决定；
- 不改变审批 API、审批链和权限校验。

## 3. 设计原则与非功能要求

### 3.1 三层反馈模型

| 层级 | 责任 | 适用场景 | 技术要求 |
|---|---|---|---|
| 短反馈层 | 告知动作完成/失败 | 所有已确定结果 | Toast 文案包含对象和动作，不承担最终状态全部解释 |
| 状态确认层 | 告知对象最终状态 | 状态推进、审批、财务更新、删除 | 列表行、详情 Sheet 或页面内状态必须更新；失败时不得伪造状态 |
| 下一步层 | 提供合理后续入口 | 存在高概率且明确的下一动作 | 优先页面内按钮或现有 Dialog；低风险保存不强制弹窗 |

### 3.2 正常路径约束

- 普通保存仍为“填写 → 保存 → 返回/保留上下文”，不增加确认页；
- 低风险保存成功后最多一个 Toast，必要时在当前页面显示状态；
- 只有业务上已经存在的后续选择（例如回款登记后的审批）才使用现有下一步 Dialog；
- 用户不应因为等待列表刷新而失去原筛选、分页、排序和滚动位置；
- 用户可通过当前页面判断“这次操作是否生效”，不依赖手动刷新。

### 3.3 反馈与状态的真实性

- “请求成功”不等于“对象最终状态已读取”；
- 写入成功但后续 GET 刷新失败时，文案必须明确“操作已提交/写入已完成，最新状态暂未获取”，不能显示完整最终状态；
- 网络超时或结果未知时，必须复用 P1 `outcomeUnknown` 语义；
- 所有成功提示使用实际对象名称/编号或稳定 ID 生成，不使用当前列表行可能已经过期的旧状态推断最终结果。

## 4. 技术方案总览

### 4.1 推荐架构

```text
页面动作 handler
  ├─ 调用现有 API / Store
  ├─ 解析成功、失败、结果未知
  ├─ 构造页面级 ActionOutcome
  ├─ 更新对象读模型（局部更新或重新查询）
  ├─ 关闭/保留 Sheet 或 Dialog
  ├─ 显示 Toast / 页面内结果
  └─ 提供可选 nextActions
          │
          ▼
列表页 / 详情 Sheet / 现有下一步 Dialog
  ├─ 维护原筛选、分页、排序和滚动上下文
  ├─ 同步当前对象和按钮可用性
  ├─ 恢复触发控件焦点
  └─ 在需要时提供下一步入口
```

页面仍然拥有业务语义和 API 调用权；共享层只提供结果类型、纯函数和少量可复用 composable。不要将所有业务动作强制抽象为一个万能 hook。

### 4.2 `ActionOutcome` 最小类型

建议新增或放入现有 `CRM-Client/src/types/` 的共享类型文件。该类型是前端 UI 收尾契约，不是后端 API 响应格式：

```ts
export type ActionOutcomeStatus = 'success' | 'unknown'

export type EntityType =
  | 'customer'
  | 'follow-up-task'
  | 'opportunity'
  | 'contract'
  | 'payment-plan'
  | 'payment-record'
  | 'invoice'
  | 'approval-task'

export interface NextAction {
  id: string
  label: string
  kind: 'view-detail' | 'continue' | 'submit-approval' | 'create-follow-up' | 'open-related'
  priority?: 'primary' | 'secondary'
  run: () => void | Promise<void>
}

export interface ActionOutcome {
  status: ActionOutcomeStatus
  entityType: EntityType
  entityId: string | number
  action: string
  message: string
  nextActions?: NextAction[]
  /** 结果未知时只能提供恢复动作，不得提供成功态下一步。 */
  recoveryAction?: 'query' | 'retry' | 'manual-confirm'
  /** 成功写入但读模型刷新失败时使用。 */
  stateSync?: 'synced' | 'pending-refresh' | 'refresh-failed'
  stateLabel?: string
}
```

实现约束：

- `run`只在页面已经判断用户可执行且对象仍有效时调用；
- `ActionOutcome` 不直接驱动全局路由；页面决定是否打开 Sheet、Dialog 或保持当前页面；
- `success` 事件可以逐步从无 payload 兼容迁移到 payload，不要求本次一次性改完所有组件；
- 后端返回的审批状态、计划状态、阶段信息优先来自 API 实际响应或刷新后的读模型。

### 4.3 组件事件契约

建议逐步统一为：

```ts
interface FormSuccessPayload {
  entityType: EntityType
  entityId: string | number
  operation: 'create' | 'update'
  outcome: 'success'
  stateSyncRequested: boolean
}

// 兼容过渡期：仍允许旧的无参数 success 事件
(e: 'success', payload?: FormSuccessPayload): void
```

Dialog 关闭职责：

- Dialog 内部负责提交成功后的自身关闭、dirty guard 放行和提交 loading 收尾；
- 父页面负责更新列表、清理编辑对象、同步详情 Sheet 和决定下一步；
- 父页面不应在收到 success 后再次执行与 Dialog 内部重复的关闭逻辑，除非是兼容旧组件的过渡代码；
- 关闭事件和 success 事件的顺序固定为：**提交成功 → 构造 payload → emit success → 组件允许关闭/发出 update:open(false)**，父页面 handler 必须可重入且不依赖事件顺序猜测。

若现有组件已经先关闭再 emit success（如部分表单组件），首期可不改正常行为，但必须在迁移任务中补测试，避免父页面在 Dialog 已卸载后读取空对象。

## 5. 页面级收尾策略

### 5.1 操作策略矩阵

| 场景 | 成功反馈 | 状态同步 | 下一步 | 上下文策略 |
|---|---|---|---|---|
| 客户创建 | “客户已创建” | 列表新增/刷新 | 可选“查看客户/新建商机” | 默认留在客户列表 |
| 客户编辑 | “客户已更新” | 当前行与详情同步 | 无则不提供 | 保留原列表/详情 |
| 跟进记录保存 | “跟进已记录” | 活动/任务重新读取 | 若有下次跟进，显示时间/入口 | 保留客户与追踪上下文 |
| 跟进完成/关闭 | “追踪已完成/已关闭” | 任务行、详情、关联活动同步 | 可选“新增跟进” | 列表操作留在列表；Sheet 操作按终态关闭 |
| 商机阶段推进 | “已推进至 X 阶段” | 当前阶段、赢率、按钮刷新 | 有下一阶段才提供继续推进语义 | 不强制跳详情 |
| 合同保存 | “合同已创建/更新” | 合同列表/详情同步 | 草稿可继续编辑 | 保留原上下文 |
| 合同提交审批 | “合同已提交审批”或实际状态 | 审批状态和按钮同步 | 可选查看审批/合同详情 | 不强制跳审批中心 |
| 回款登记 | 现有金额/剩余金额/计划状态摘要 | 计划、记录、合同回款状态同步 | 保留 `PaymentNextStepDialog` | 由现有 Dialog 决定 |
| 回款记录编辑/重提 | 实际操作结果 | 记录详情、审批、列表同步 | 按现有审批结果提供入口 | 优先保留详情 Sheet |
| 删除 | “对象已删除” | 从列表移除，详情清理 | 必要时回到列表 | 保留筛选和分页，焦点回到合理位置 |
| 审批中心单条审批 | 单条动作结果及对象状态 | 审批任务和业务对象刷新 | 按单条结果提供查看详情或重试 | 不关闭用户正在查看的无关对象 |

### 5.2 成功结果处理顺序

所有改造页面遵循以下逻辑顺序：

1. 防止同一对象同一动作重复提交；
2. 调用现有写 API / Store action；
3. 捕获结果未知，不进入成功分支；
4. 从写响应提取对象状态；若没有完整对象，按对象 ID重新查询；
5. 更新列表行、详情对象或关联读模型；
6. 根据入口决定关闭或保留 Dialog/Sheet；
7. 显示短反馈；若需要，显示页面内状态或下一步入口；
8. 恢复原触发控件焦点；
9. 清理 pending key、临时选择和过渡状态。

若第 4/5 步刷新失败：

- 不回滚已经成功的写入；
- Toast 说明写入已经完成但最新状态暂未刷新；
- 当前列表显示的数据可保留，但必须提供刷新/重试入口；
- 禁止继续使用旧对象状态决定高风险按钮的可用性，必要时暂时禁用并要求刷新。

## 6. 关键页面技术细化

### 6.1 Customers.vue / CustomerFormDialog.vue

**改造点：**

1. `CustomerFormDialog` 的 `success` 增加可选 payload：客户 ID、create/update、对象名称（如果已在表单/响应中可得）；
2. `Customers.vue` 的 `handleCustomerFormSuccess` 接收 payload：
   - 当前分页中存在该行时优先局部替换；
   - 新建或当前行不在内时执行一次列表刷新；
   - 当前详情 Sheet 已打开且 ID相同，通知 Sheet 刷新；
3. 统一 Toast 文案由 Dialog 或页面二选一负责，避免同一次操作出现两个成功提示；
4. 创建后是否展示“查看客户/新建商机”由产品开关或页面入口决定，本期默认不增加第二个弹窗；
5. 保持现有编辑前置详情加载方案，不把编辑改回先开空弹窗再加载。

**验收重点：**

- 编辑客户成功后列表行无需手动刷新即可显示新名称/状态；
- 从客户详情进入编辑，保存后详情 Sheet仍在同一客户上下文；
- 创建客户成功后不会自动跳离客户列表；
- 失败或结果未知时表单内容和原上下文保留。

### 6.2 CustomerTracking.vue / FollowUpFormDialog.vue

**改造点：**

1. 将 `transitionTask` 的成功处理抽成页面级 `completeTaskOutcome`/`closeTaskOutcome`，统一读取最终任务；
2. 从 Sheet 操作终态任务时，先确定写成功，再关闭 Sheet；关闭后刷新任务列表；
3. 从列表操作时，保持筛选、分页、排序和当前列表滚动，更新对应任务行；
4. `handleFollowUpSuccess(completedTaskPublicId)` 保留 task ID 语义，并补充活动/任务状态刷新结果；
5. 对“提交并完成追踪”显示组合结果：活动已添加、追踪已完成；不可拆成两个 Toast；
6. `resolvePendingConfirmation` 继续使用现有 confirmation API/Store，不新增第二个确认弹窗；若终态完成，沿用清空 Sheet + 刷新读模型；
7. 对失败后列表刷新失败提供页面内重试，不把刷新失败误报为动作失败。

**状态映射：**

| API 结果 | 任务状态 | UI 处理 |
|---|---|---|
| transition 成功 | `COMPLETED` | 状态徽章更新为已完成，终态动作消失 |
| transition 成功 | `CANCELLED` | 状态徽章更新为已关闭，终态动作消失 |
| 结果未知 | 未确认 | 使用 P1 查询/重试/人工确认，不关闭为成功 |
| 写入成功、详情 GET失败 | 未知最新读模型 | 说明已提交，提供刷新任务列表 |

### 6.3 Opportunities.vue

**改造点：**

1. `handleAdvanceStage` 成功后构造包含目标阶段的结果；优先使用 `moveOpportunityStage` 响应，否则重新获取商机详情/列表；
2. 更新当前列表行的阶段、赢率和 action visibility；全量刷新作为兜底；
3. 若商机详情 Sheet正在展示同一 ID，触发详情刷新；
4. 对“起始阶段已设置”和“阶段已推进”使用同一结构的结果文案，但动作词保持业务准确；
5. 最终阶段提示采用 info/warning 语义，明确“当前已经是最终阶段”，不显示为系统异常；
6. 继续保留原确认操作和权限判断。

**不改：**

- 不改变采购阶段排序和推进 API；
- 不自动连续推进多个阶段；
- 不因为推进成功强制跳转详情或审批中心。

### 6.4 Contracts.vue / ContractFormDialog.vue

**改造点：**

1. 创建/编辑 success payload 至少携带合同 ID和 operation；
2. `handleSubmitApproval` 使用行级 pending 集合，成功后以审批 API/合同刷新结果确定状态；
3. 若响应能确定审批状态，页面内展示“审批中/已通过/已转财务确认”等真实状态；若不能确定，显示“已提交，请刷新确认”；
4. 合同列表和详情 Sheet使用同一合同 ID同步；
5. 保持合同附件校验、审批权限和删除约束不变。

### 6.5 PaymentPlans.vue / PaymentRecords.vue

**改造点：**

1. 将 `PaymentPlans.vue` 当前完整的回款登记收尾记录为参考实现，优先提取纯函数：金额格式化、计划状态标签、结果摘要构造；
2. 不再新增同目的结果 Dialog；
3. `PaymentPlanFormDialog` success payload 补充计划 ID和 create/update；
4. `PaymentRecords.vue` 的编辑、重提审批和删除分别维护 action key，避免“编辑中”阻塞或误影响详情 Sheet；
5. 写入后先刷新记录，再按详情 Sheet是否仍打开决定更新 `selectedRecord` 或清理选择；
6. 重新提交审批使用实际审批响应决定提示，不用固定文案覆盖直接确认和进入审批两种结果；
7. 继续保留回款登记的幂等 key和结果未知恢复查询。

### 6.6 ApprovalCenter.vue

**改造点：**

1. 仅保留单条审批、单条结果反馈和 409 冲突处理；
2. 将成功结果按对象维度整理为可定位摘要：成功数量、失败数量、可刷新对象；
3. 单条审批后刷新审批任务和关联合同/发票对象；
4. 详情 Sheet打开时同步当前对象；若对象因状态改变不再匹配当前筛选，显示“对象已更新，当前列表已重新筛选”，不默默丢失反馈；
5. 不把审批中心变成所有业务提交后的强制落点。

## 7. Sheet、Dialog、列表与焦点恢复

### 7.1 上下文记录

页面在打开详情 Sheet 或编辑 Dialog 时记录最小上下文：

```ts
interface ReturnContext {
  source: 'list' | 'detail-sheet' | 'route'
  entityType: EntityType
  entityId: string | number
  triggerId?: string
  listState?: {
    page: number
    pageSize: number
    filters: unknown
    sorts: unknown
  }
}
```

实现要求：

- 只保存当前页面需要的上下文，不做全局历史栈；
- 筛选、分页、排序由页面现有状态负责，不能因为收尾重置；
- `triggerId` 使用稳定 DOM ID 或可恢复的表格行动作标识，不使用易变的索引；
- 详情 Sheet 内打开 Dialog时，关闭 Dialog后先回到 Sheet，不跳列表；
- 从列表打开 Dialog时，保存成功/取消后回到原列表，不自动打开详情，除非用户明确点击“查看详情”。

### 7.2 焦点规则

- 打开 Dialog/Sheet 前记录触发控件；
- 成功关闭后优先将焦点返回触发控件；
- 若对象已被删除或从当前筛选结果移除，焦点回到表格容器、分页控件或页面标题区域；
- 若存在页面内下一步入口且用户点击了该入口，焦点进入下一步目标控件；
- 复用 `useDialogCloseGuard` 已有的焦点保存/恢复能力，不为本期重新实现一套 Dialog focus trap；
- 视觉滚动位置与焦点恢复分开处理，恢复焦点不得把用户强行滚到页面顶部。

### 7.3 关闭职责

| 场景 | 组件职责 | 页面职责 |
|---|---|---|
| Dialog内部成功 | 清理 submitting、放行 close guard、关闭自身、emit success | 同步对象、列表和详情 |
| 用户取消且无修改 | 关闭自身 | 清理选择状态 |
| 用户取消且有修改 | 展示现有 guard | 不直接清空表单 |
| Sheet内动作成功 | 根据动作策略关闭/保留 | 刷新列表和关联对象 |
| 父页面刷新 | 不强制关闭仍可用的 Sheet/Dialog | 传入最新对象或触发 refresh |

## 8. API、状态和数据契约影响

### 8.1 API 影响

本期原则上**不新增、不修改后端 API**。继续使用现有：

- 客户 CRUD 与详情接口；
- 跟进活动创建、任务 transition、待确认 resolve；
- 商机采购阶段查询与阶段推进；
- 合同 CRUD 与通用审批提交；
- 回款计划/回款记录 CRUD、幂等和恢复查询；
- 审批中心单条动作和对象详情刷新。

如果某个写接口当前没有返回对象状态，前端可在成功后按 ID执行一次 GET；不得把本地旧对象直接当作最终状态。只有当重复 GET造成明确性能问题且后端已有稳定响应字段时，才另行提出 API 优化，不在本 TRD默认扩大范围。

### 8.2 前端状态影响

推荐新增的最小状态：

- 页面级 `pendingActionKeys: Set<string>`，key 格式为 `entityType:entityId:action`；
- 页面级 `lastActionOutcome: ActionOutcome | null`，只在需要持久反馈的页面使用；
- `ReturnContext` 或等价页面私有状态；
- `ActionOutcome` / `NextAction` 类型；
- 如多个页面重复“写成功后刷新对象”，可新增小型纯 composable，但不得把业务 API 调用隐藏到无法追踪的全局 hook。

### 8.3 与现有错误体系的关系

继续复用：

- `FeedbackError`、`toFeedbackError`；
- `handleApiError`；
- `request.ts` 只处理 401，其它错误由页面处理；
- `outcomeUnknown`、`canRefresh`、`canReopen` 等 P1 字段。

新增结果类型不得复制一份错误模型。错误仍由 `FeedbackError` 表达，动作结果由 `ActionOutcome` 表达；结果未知时通过 `ActionOutcome.status = 'unknown'` 关联恢复动作。

## 9. 错误、超时和并发处理

### 9.1 失败分类

| 情况 | 用户看到的语义 | 页面行为 |
|---|---|---|
| 表单校验失败 | 请修正字段 | Dialog 保留，定位首个错误 |
| 权限失败 | 无权执行该动作 | 保留上下文，刷新动作权限或隐藏已不可用操作 |
| 404 | 对象不存在/已被删除 | 刷新列表，关闭无效 Sheet，说明对象已不存在 |
| 409 | 对象已发生变化 | 沿用 P1 冲突提示，刷新后允许用户重新判断 |
| 5xx/网络失败 | 操作未确认或暂时失败 | 按错误类型提供重试，不显示成功 |
| 写入成功、读取失败 | 已完成但最新状态暂未获取 | 显示 pending-refresh，提供刷新 |

### 9.2 重复提交

- 所有状态推进、审批提交、删除、回款写入使用 action key 或已有幂等机制；
- 同一行 pending 时按钮禁用或显示 loading；
- 列表刷新不能清除仍在提交中的 pending key；
- Dialog 关闭不能中断正在进行的写操作，除非现有业务明确支持取消请求。

### 9.3 结果未知

统一遵循：

```text
写请求超时/网络断开
    ↓
标记 outcomeUnknown
    ↓
使用已有幂等 key或对象 ID查询
    ├─ 确认已写入：进入成功+状态同步
    ├─ 确认未写入：允许重试
    └─ 仍无法确认：人工确认/刷新，不宣称成功
```

回款登记现有恢复查询逻辑作为标准；其它对象若没有幂等恢复 API，不得自行模拟“肯定未提交”，应使用“结果暂未确认，请刷新/稍后重试”。

## 10. 组件和文件改造清单

### 10.1 主要页面

- `CRM-Client/src/views/Customers.vue`
- `CRM-Client/src/views/CustomerTracking.vue`
- `CRM-Client/src/views/Opportunities.vue`
- `CRM-Client/src/views/Contracts.vue`
- `CRM-Client/src/views/PaymentPlans.vue`
- `CRM-Client/src/views/PaymentRecords.vue`
- `CRM-Client/src/views/ApprovalCenter.vue`

### 10.2 主要表单/详情组件

- `CRM-Client/src/components/dialogs/CustomerFormDialog.vue`
- `CRM-Client/src/components/dialogs/FollowUpFormDialog.vue`
- `CRM-Client/src/components/dialogs/OpportunityFormDialog.vue`
- `CRM-Client/src/components/dialogs/ContractFormDialog.vue`
- `CRM-Client/src/components/dialogs/PaymentPlanFormDialog.vue`
- `CRM-Client/src/components/dialogs/PaymentRecordDialog.vue`
- `CRM-Client/src/components/PaymentNextStepDialog.vue`（仅复用/必要时抽取纯逻辑，不替换）
- `CRM-Client/src/views/CustomerDetailSheet.vue`
- `CRM-Client/src/views/OpportunityDetailSheet.vue`
- `CRM-Client/src/views/ContractDetailSheet.vue`
- `CRM-Client/src/components/panels/OpportunityDetailContent.vue`

### 10.3 共享类型/工具候选

- `CRM-Client/src/types/actionOutcome.ts`（建议新增）
- `CRM-Client/src/composables/useActionOutcome.ts`（仅在出现至少两个稳定复用点后新增）
- `CRM-Client/src/types/feedback.ts`（只做类型关联，不复制错误处理）
- 现有 `CRM-Client/src/utils/errorHandler.ts`、`request.ts`（保持职责，不新增全局 Toast）

## 11. 详细时序

### 11.1 普通表单保存

```text
用户点击保存
  → 表单校验
  → 设置 dialog/entity pending
  → 调用 create/update API
  → 成功取得 entityId
  → 关闭 Dialog（保留返回上下文）
  → 父页面收到 success payload
  → 局部更新或按 ID刷新
  → Toast“对象已保存”
  → 恢复触发控件焦点
```

### 11.2 状态推进/审批提交

```text
用户点击动作
  → 现有确认流程（如有）
  → 设置行级 pending
  → 调用现有 transition/approval API
  → 读取响应中的状态或按 ID重新查询
  → 更新列表行和已打开详情
  → Toast + 页面内状态
  → 动作按钮按最新状态重新计算
  → 清理 pending，恢复焦点
```

### 11.3 回款登记

```text
用户提交回款登记
  → PaymentRecordDialog 校验
  → PaymentPlans.handleRegisterSubmit
  → idempotency key写入
  → 成功或结果未知恢复查询
  → 获取更新后的计划详情
  → 生成金额/剩余/计划状态摘要
  → 关闭登记 Dialog
  → 刷新计划列表
  → 保留现有 PaymentNextStepDialog 的审批/详情入口
```

## 12. 测试方案

### 12.1 单元测试

- `ActionOutcome` 构造、成功/未知分支和状态标签映射；
- action key 在同一对象重复点击时只执行一次；
- `nextActions` 在结果未知时不生成；
- 成功但刷新失败时生成 `stateSync = 'refresh-failed'`；
- 分页、筛选、排序状态在刷新前后保持不变；
- 详情 Sheet 当前 ID与 success payload ID不一致时不误更新；
- 焦点目标已卸载时使用安全 fallback。

### 12.2 页面行为测试

至少覆盖：

1. 客户编辑保存：列表行更新、Toast一次、无额外弹窗；
2. 客户创建：停留列表，上下文不被重置；
3. 客户追踪完成：列表入口和 Sheet入口分别符合收尾规则；
4. “提交并完成追踪”：活动和任务结果只显示组合反馈；
5. 商机阶段推进：目标阶段和动作按钮更新；
6. 合同提交审批：按钮防重复，审批状态按真实结果显示；
7. 回款登记：现有金额/剩余金额/计划状态摘要和下一步 Dialog不回归；
8. 回款记录编辑/重提：详情 Sheet、Dialog、列表同步；
9. 审批中心单条审批：每条成功/失败结果可定位；
10. 写成功但刷新失败：不误报失败，也不伪造最终状态；
11. 结果未知：不出现成功 Toast，可查询/重试/人工确认；
12. 删除：对象从列表消失，焦点回到合理位置。

### 12.3 无障碍与响应式

- Toast 保持 `aria-live` 语义，避免重复读屏；
- Dialog/Sheet关闭后焦点可恢复；
- 下一步入口键盘可达、按钮名称明确；
- 320px宽度和 200%缩放下不依赖操作列展示全部长文案；
- 不用颜色作为状态唯一表达；
- 状态变化对读屏用户提供文本反馈。

## 13. 灰度、监控和回滚

### 13.1 灰度策略

建议按页面分批：

1. 先迁移客户编辑、商机阶段推进等低风险列表动作；
2. 再迁移客户追踪完成、合同审批；
3. 最后对齐回款记录和审批中心，保持回款登记现有实现不变；
4. 每批次完成关键任务验收后再迁移下一批。

### 13.2 可观测字段

如项目已有 UX telemetry 接缝，可记录：

- `entity_type`、`action`、`source`（list/sheet/dialog）；
- `outcome`（success/failure/unknown）；
- `state_sync`（synced/pending-refresh/refresh-failed）；
- `next_action_shown`、`next_action_clicked`；
- `return_context_restored`、`focus_restored`；
- 不记录客户名称、合同内容、回款备注等敏感业务内容。

本 TRD不要求为此新增完整埋点系统；若暂时没有统一采集链路，可以先保留结构化日志或测试断言。

### 13.3 回滚策略

- 新结果 payload 为可选，旧组件仍可使用无参数 success；
- 新增结果摘要或下一步入口按页面开关/局部组件启用；
- 发现列表刷新、Sheet关闭或焦点回归回归时，可关闭页面适配而不回滚业务 API；
- 不回滚已经成功的业务数据，只回滚 UI收尾逻辑。

## 14. 验收矩阵

| 验收项 | 通过标准 | 代表页面 |
|---|---|---|
| 成功结果明确 | 用户能看到动作、对象和结果 | Customers / Contracts |
| 对象状态同步 | 列表、详情、按钮不长期停留旧状态 | Tracking / Opportunities / Contracts |
| 下一步合理 | 只在明确需要时出现，不强制跳转 | PaymentPlans / ApprovalCenter |
| 正常路径短 | 普通保存不新增确认页或二次弹窗 | Customers / PaymentPlans |
| 上下文保留 | 筛选、分页、排序、Sheet层级保持可预测 | 全部列表页 |
| 焦点可恢复 | 关闭后回到触发控件或安全 fallback | Customers / Tracking / PaymentRecords |
| 失败真实 | 失败、超时、刷新失败不误报成功 | 全部写操作 |
| 结果未知可恢复 | 有查询、重试或人工确认语义 | PaymentPlans / PaymentRecords |
| 防重复提交 | 同一对象同一动作不会并发执行两次 | Opportunities / Contracts / ApprovalCenter |
| 已实现能力不回归 | 回款摘要和下一步 Dialog继续可用 | PaymentPlans |
| P1边界不被破坏 | 高风险确认、错误恢复、并发冲突仍按P1规则 | Tracking / Contracts / ApprovalCenter |

## 15. 待业务确认事项

以下问题不应由前端自行猜测，开发前需要产品/业务负责人确认：

1. 客户创建成功后，不同角色是否都需要“新建商机”入口，还是仅销售角色显示；
2. 跟进完成后，默认下一步是“新增跟进”、查看客户详情，还是仅留在列表；
3. 商机最终阶段推进后是否存在业务动作（例如提交审批），以及不同采购流程是否不同；
4. 合同提交审批后，哪些角色可以看到“查看审批”，何时可显示“已直接确认”；
5. 回款登记后的审批入口是否对所有角色一致，是否允许部分回款后立即提交；
6. 删除对象后焦点的业务优先级：回到相邻行、列表工具栏还是页面标题；
7. 详情 Sheet内完成终态动作后，是否统一关闭 Sheet，还是某些角色/页面需要继续停留查看关联信息。

## 16. 实施顺序建议

### Phase 1：建立最小结果契约

- 新增 `ActionOutcome`/`NextAction` 类型；
- 约定 success payload 兼容形式；
- 提取回款登记结果摘要中的纯函数或测试样例；
- 为结果未知和刷新失败补充测试。

### Phase 2：迁移低风险保存

- 客户、商机、合同、回款计划表单；
- 统一 success payload、父页面局部更新/刷新兜底；
- 验证不增加弹窗和跳转。

### Phase 3：迁移状态推进与审批

- 客户追踪完成/关闭；
- 商机阶段推进；
- 合同审批；
- 审批中心单条结果。

### Phase 4：财务链路对齐

- 回款记录编辑/重提审批；
- 发票相关常规保存；
- 保持回款登记现有闭环不回归。

### Phase 5：验收与观测

- 关键任务端到端验收；
- 异常注入、网络超时、409、刷新失败；
- 键盘/读屏/移动端验收；
- 评估是否需要启用 telemetry，不以埋点作为本期上线阻塞条件。

## 17. 最终边界

本 TRD的交付标准是：用户完成一个动作后，能够在当前上下文中可靠回答“刚才做了什么、对象现在怎样、我是否需要继续做什么”。

它不是一次全系统导航重构，也不是把每个成功操作都变成弹窗。实现应优先复用现有页面、API、错误体系、`useDialogCloseGuard`、Sheet/Dialog模式和 `PaymentNextStepDialog`，只补齐对象级结果、上下文恢复、状态同步和必要的下一步入口。
