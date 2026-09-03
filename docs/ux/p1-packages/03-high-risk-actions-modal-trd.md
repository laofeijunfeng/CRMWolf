# P1-PKG-03 高风险操作与弹窗统一 TRD

- **文档类型**：Technical Requirements Document（技术需求文档）
- **所属改造包**：P1-PKG-03 高风险操作与弹窗统一
- **优先级**：P1
- **版本**：v1.0
- **日期**：2026-09-03
- **适用系统**：CRMWolf 非 Agent / AI 自动化业务链路
- **来源 PRD**：[飞书文档：P1-PKG-03 高风险操作与弹窗统一](https://apifox666.feishu.cn/wiki/RJaowVHVBisaZbkRWVQcSyVOn1e)
- **关联设计规范**：`CRM-Docs/design-system/components/modal-sheet.md`、`CRM-Docs/design-system/foundations/accessibility.md`、`CRM-Docs/design-system/patterns/list-page.md`
- **排除范围**：Agent / AI 自动化，包括 Agent 专属 UI、异步 operation/job 协议和 Agent 工作流确认链路

> 本 TRD 只新增技术设计文档，不直接修改业务代码。实施时必须避开当前工作区中与 Agent、客户活动工作流、P1-PKG-01、P1-PKG-02 相关的未提交改动。

## 1. 技术结论

### 1.1 总体结论

系统当前不存在“所有弹窗都不可用”的 P0 级阻断，但高风险操作在承载组件、确认信息、提交互斥、错误恢复、焦点管理和移动端适配方面存在较多 P1 问题。问题集中在以下几类：

1. `Customers.vue` 仍使用自定义临时 modal，和设计系统的 Dialog 语义、焦点、Escape、关闭保护不一致。
2. 全局 `confirmDialog` 是单例 Promise 状态，存在并发调用覆盖 `resolve` 的结构性风险。
3. 普通删除、状态变更和审批动作的确认内容过于简短，缺少对象、当前状态、目标状态和影响范围。
4. 多数高风险写操作只通过 Toast 反馈，未统一处理提交中、重复点击、权限失败、409 冲突和结果未知。
5. 客户列表中的高风险动作主要通过桌面右键菜单发现，移动端和详情场景的可发现性不足。
6. 已存在的业务型 Dialog（客户移交、发票冲红、回款登记）已经承载关键字段复核，若再套一层确认会明显拉长路径，属于过度优化。

### 1.2 路径结论：不会全面拉长正常操作路径

本期不采用“所有高风险操作统一增加确认页 + 确认弹窗”的方案，而采用“信息更完整、步骤不额外增加”的方案：

- 退回公海、标记输单：保留现有理由填写步骤，只将临时 modal 迁移为规范 Dialog，不新增二次确认。
- 客户移交、发票冲红、回款登记：保留现有业务 Dialog，在同一浮层内补充影响范围、状态和结果反馈，不再包裹第二层确认。
- 纯删除、撤回等不可逆或高影响操作：保留一次确认；确认内容更完整，但不增加额外页面。
- 审批同意：详情页优先采用一次点击 + 提交互斥 + 最终状态反馈，不强制增加确认弹窗；列表页快速审批保留轻量确认以降低误触风险。
- 批量审批：已有批量 Dialog，不新增确认页，仅补齐业务类型、数量、影响和部分成功结果。

因此，**正常路径不会被全面拉长**；变化主要是统一承载、补充关键上下文和改善异常路径。只有确实存在不可逆、批量或并发风险的动作才保留确认。

### 1.3 后端结论

本期原则上不改业务状态机和既有 API。优先复用当前后端已有的：

- 权限校验；
- 状态限制；
- 审批并发校验；
- 操作审计；
- 回款 `Idempotency-Key` 和结果确认接口；
- 业务通知机制。

仅在联调发现“前端无法查询最终状态”或“同一错误无法稳定区分”时，才补充最小 API/错误码契约，不建设一套新的全局事务编排系统。

## 2. PRD 转技术范围

### 2.1 纳入范围

| 领域 | 纳入内容 |
| --- | --- |
| 浮层承载 | Dialog、AlertDialog、Sheet 的选型和统一行为 |
| 高风险确认 | 删除、退回公海、标记输单、失效、撤回、驳回、快速审批等 |
| 业务型 Dialog | 客户移交、发票冲红、回款登记等已有表单浮层的规范化 |
| 反馈状态 | confirming、submitting、success、failed、conflict、unknown 的最小状态语义 |
| 关闭行为 | Escape、遮罩、关闭按钮、未保存保护、焦点恢复 |
| 响应式 | 窄视口内容滚动、按钮可达、无页面横向溢出 |
| 错误恢复 | 校验、权限、网络、冲突、服务失败和结果未知的动作建议 |
| 发现性 | 高风险动作不能只隐藏在桌面右键菜单 |
| 测试 | 组件、页面关键路径、异常和可访问性回归 |

### 2.2 不纳入范围

- Agent / AI 自动化及其操作确认链路；
- 全量页面 IA 重构；
- 统一重写所有业务表单 Dialog；
- 为每个普通保存操作增加确认；
- 通用撤销/回滚平台；
- 跨页面持久化任务中心；
- 改变客户、合同、发票、回款和审批的业务状态机；
- 直接把所有右键动作提升成页面主按钮；
- 本期新增数据库表或操作事务日志体系；
- 通过前端文案替代后端权限和状态校验。

## 3. 系统现状与问题证据

### 3.1 浮层实现分布

当前系统同时存在：

- 基于 Reka/shadcn-vue 的 `Dialog`；
- 用于不可逆确认的 `AlertDialog`；
- 详情场景使用的 `Sheet`；
- 全局 Promise 形式的 `ConfirmDialog`；
- 页面内手写的 `div.modal-overlay`。

多种承载方式本身不是问题，问题在于缺少明确的技术边界：哪些动作需要阻断确认、哪些动作是表单型业务 Dialog、哪些场景必须保留页面参照，以及所有浮层应该如何统一处理关闭、焦点、提交中和异常。

### 3.2 Customers 临时 modal

证据：`CRM-Client/src/views/Customers.vue:128-139`、`:631-670`、`:685-706`、`:990-1040`、`:1181-1246`。

当前实现：

- `returnModalVisible`、`loseModalVisible` 和表单状态均由页面私有状态管理；
- 退回公海、标记输单通过手写 `div` 和 `@click` 遮罩关闭；
- 关闭按钮直接改状态，没有未保存保护；
- 未声明 `DialogTitle` / `DialogDescription` 语义关系；
- 提交期间没有独立的 submitting 锁；
- 校验错误只通过 Toast 展示，无法将错误关联到字段；
- `.modal-content` 使用 `min-width: 400px`，存在窄屏溢出风险；
- 文件内明确注释为“临时样式，后续替换为 shadcn-vue Dialog”。

技术判断：这是本包最明确的第一批迁移对象。迁移应保留原有业务字段和 API 调用，不改变退回公海/输单的业务流程。

### 3.3 全局 confirmDialog 单例风险

证据：

- `CRM-Client/src/utils/confirmDialog.ts:26-68`；
- `CRM-Client/src/utils/confirmDialogImpl.ts:17-68`；
- `CRM-Client/src/components/crmwolf/ConfirmDialog.vue:1-48`。

当前 `confirmDialogState` 只保存一个 `resolve`：

```ts
resolve: ((value: boolean) => void) | null
```

新的 `createConfirmDialog()` 会直接覆盖当前状态。如果两个操作在前一个 Promise 完成前同时调用确认，后一个操作可能覆盖前一个的回调，造成前一个 Promise 永不返回或返回结果归属错误。

同时，当前选项只有 `message`、`title`、`confirmText`、`cancelText`、`variant`，不能表达：

- 对象名称和类型；
- 当前状态、目标状态；
- 影响范围；
- 理由输入和校验；
- 异步提交状态；
- 冲突、未知结果和恢复路径。

技术判断：不能简单把现有 `confirmDialog()` 的参数继续堆叠。应增加结构化高风险动作能力，同时保留旧函数签名作为兼容入口，分批迁移调用点。单例实现至少要改为“有界队列或显式拒绝并发调用”，不能让 Promise 静默悬挂。

### 3.4 普通删除与状态变更

`Customers.vue:618-732` 当前对领取、赢单、失效和删除多使用简单确认：

```ts
const confirmed = await confirmDialog(...)
```

确认后通常直接调用 API，成功后 Toast + 刷新列表。主要差异：

- 领取、赢单、失效和删除的确认文案不统一；
- 没有稳定显示当前状态和目标状态；
- 成功消息通常不包含对象名称和最终状态；
- 列表页删除没有独立 pending 状态；
- 失败主要交给 Toast，Dialog 上下文已消失；
- 未统一处理 409、权限不足和结果未知。

系统中类似调用还分布于：

- `CRM-Client/src/views/Invoices.vue`；
- `CRM-Client/src/views/InvoiceDetailSheet.vue`；
- `CRM-Client/src/views/Contracts.vue`；
- `CRM-Client/src/views/PaymentPlans.vue`；
- `CRM-Client/src/views/PaymentRecords.vue`；
- `CRM-Client/src/views/CustomerTracking.vue`；
- `CRM-Client/src/views/Opportunities.vue`；
- `CRM-Client/src/components/FollowUpList.vue`；
- `CRM-Client/src/components/system-config/*`。

### 3.5 后端真实业务影响并不相同

确认组件不能使用一套“此操作不可恢复”的通用文案覆盖所有删除动作。

| 对象 | 后端约束/影响 | 技术要求 |
| --- | --- | --- |
| 客户 | `DELETE /customers/{customer_id}` 为逻辑删除，需权限校验，存在档案投影清理和操作审计 | 确认对象、权限和关联数据影响；成功反馈实际对象和最终状态 |
| 合同 | 仅草稿且不在审批中/已通过等状态时可删；相关回款计划会一并清理，且不可恢复 | 确认摘要必须明确“关联回款计划会被清理” |
| 回款计划 | 有关联回款记录时不能删除；删除后不可恢复 | 确认前展示当前状态/关联回款限制；409/业务失败保留上下文 |
| 回款记录 | 审批中/审批通过后不可删；删除后会重新计算计划和合同回款状态 | 明确金额汇总和状态重算影响；成功后刷新计划与合同状态 |
| 发票申请 | 列表和详情 Sheet 均可删除；详情已有 deleting 状态，列表实现不一致 | 统一确认摘要、pending 和成功后的关闭/刷新策略 |
| 客户退回公海 | 解除负责人绑定，可能触发飞书通知/业务状态变化 | 展示当前状态、目标状态、负责人解除和通知影响 |
| 客户输单 | 必须有输单原因；重复标记已输单返回 400；可能触发通知 | 理由必须是 Dialog 内字段级校验；重复提交不应清空原因 |
| 客户移交 | 可选择仅客户、客户+跟进中商机、客户+全部商机，后两者可能同步合同 | 在已有 Dialog 内展示影响范围预览，不新增二次确认 |
| 发票冲红 | 原蓝字发票会标记为已冲红；需要冲红原因、红字号码和红字文件 | 现有表单型 Dialog 规范化，不再包二次 AlertDialog |

后端证据：

- `CRM-Server/app/api/customers.py:1444-1535`、`:1679-1833`；
- `CRM-Server/app/api/contracts.py:942-978`；
- `CRM-Server/app/api/payments.py:891-1058`、`:1242-1360`；
- `CRM-Server/app/api/invoices.py` 发票申请相关路由；
- `CRM-Client/src/views/InvoiceDetailSheet.vue:1414-1462`。

### 3.6 审批动作存在“已有基础但语义不一致”

证据：`CRM-Client/src/components/ApprovalProcessGeneric.vue:105-115`、`:230-271`、`:385-494`；`CRM-Client/src/views/ApprovalCenter.vue:478-545`、`:701-708`、`:1398-1426`、`:1707-1765`。

`ApprovalProcessGeneric.vue` 已具备：

- `actionPending`；
- 驳回理由 Dialog；
- 撤回 AlertDialog；
- 409 冲突后刷新；
- 驳回理由保留；
- 批量审批部分成功和失败重试基础。

但当前仍有以下不一致：

- 同意直接调用 `handleApprove()`，没有确认摘要；
- 撤回文案缺少对象名称、当前状态和目标状态；
- 驳回是普通 Dialog，撤回是 AlertDialog，结构和关闭语义不统一；
- 提交审批动作没有统一的高风险交互规则；
- 详情页、审批中心和移动端快速审批的确认策略不同；
- 批量结果需要明确实体类型、数量、成功/失败/他人已处理三类结果。

技术判断：审批包不应重写已有并发和部分成功机制，只统一其文案、状态、焦点和错误语义。

### 3.7 业务型 Dialog 不应重复包确认

#### 客户移交

`CRM-Client/src/components/dialogs/CustomerTransferDialog.vue:32-155` 已是独立业务 Dialog，具备负责人、移交范围、备注和 submitting 状态；后端响应还返回移交商机/合同数量。应增加影响范围预览和成功摘要，但不增加二次确认页。

#### 发票冲红

`CRM-Client/src/views/InvoiceDetailSheet.vue:1414-1462` 已包含原因、红字号码、文件上传、必填校验、提交中禁用和冲红后果说明。这已经是“复核 + 提交”的业务表单，不应再叠加确认弹窗。

#### 回款登记

`CRM-Client/src/views/PaymentPlans.vue`、`PaymentPlanDetailSheet.vue` 和 `CRM-Client/src/api/payment.ts` 已有 `crypto.randomUUID()`、`Idempotency-Key` 和结果未知后的查询路径。新高风险交互必须复用现有幂等键，不能二次生成一个新的操作 ID，也不能在结果未知时直接引导用户重新登记。

## 4. 设计原则与决策

### 4.1 Dialog / AlertDialog / Sheet 选型

| 承载 | 用途 | 本期典型场景 | 不适用场景 |
| --- | --- | --- | --- |
| `Dialog` | 需要输入、复核或完成短时业务任务 | 退回公海、标记输单、客户移交、驳回、发票冲红 | 纯不可逆确认但没有输入 |
| `AlertDialog` | 不可逆/高影响操作的最后确认 | 删除、撤回、列表快速同意 | 已经包含完整字段复核的业务表单 |
| `Sheet` | 需要保留页面参照的详情或较长任务 | 客户详情、发票详情、审批业务详情 | 用来替代确认或长期页面 |

实现必须复用现有 `@/components/ui/dialog`、`@/components/ui/alert-dialog` 和 `@/components/ui/sheet`，不新增 Element Plus 或手写 focus trap。

### 4.2 一次确认 vs 复核型业务 Dialog

采用以下判定规则：

1. **只有一个明确的不可逆动作，且不需要用户输入**：使用一次 `AlertDialog`。
2. **需要填写理由、上传附件、选择负责人/范围或复核多个字段**：使用一个业务 `Dialog`，将影响摘要和字段校验放在同一层。
3. **当前详情页已经展示完整对象上下文，且动作可由服务端状态保护**：可采用一次点击 + pending + 最终状态，不强制二次确认。
4. **批量动作**：在现有批量 Dialog 中展示数量、业务类型、失败策略，不再新增确认页。
5. **不允许“Dialog 内点击提交后再弹 AlertDialog”作为默认模式**。只有当提交前后风险语义完全不同且 PRD 明确要求时才例外。

### 4.3 高风险操作的可发现性

遵循列表页规范：

- 桌面端可以保留右键菜单作为快捷入口；
- 客户详情顶部/操作区需提供当前状态下可用的高风险动作入口；
- 移动端必须通过可见菜单或卡片底部操作入口访问；
- 不把所有高风险动作提升为主按钮，主按钮只保留当前任务最重要动作；
- 动作根据状态和权限动态显示，禁止把不可用动作展示为可点击后再由 Toast 解释。

### 4.4 关闭、Escape、焦点和未保存保护

所有新迁移的 Dialog/AlertDialog 必须满足：

- 打开后焦点进入浮层；
- 关闭后焦点返回触发按钮；
- Escape 等价于取消，不等价于确认；
- 不可逆确认不得因遮罩点击直接执行；
- 有输入且输入非空时，遮罩、关闭按钮和 Escape 触发未保存保护；
- submitting 或结果确认中禁止关闭，避免用户离开后重复操作；
- 关闭保护不能清空用户输入，除非用户明确确认放弃；
- 错误后焦点移动到首个需要处理的字段，错误与字段通过 `aria-describedby` 或等价语义关联；
- Dialog 内内容区域可滚动，页面背景不得横向滚动；
- 组件必须使用语义标题、描述、按钮名称和实时结果区域。

底层焦点管理由 Reka/shadcn 组件负责，业务代码只负责正确使用受控 `open`、关闭原因和触发元素引用，不自行实现全局 focus trap。

### 4.5 提交中和防重复提交

每个高风险写操作都必须有局部 mutation 状态，至少具备：

```ts
type MutationOutcome =
  | 'idle'
  | 'confirming'
  | 'submitting'
  | 'success'
  | 'failed'
  | 'conflict'
  | 'unknown'
```

实现可在组件内部使用布尔值组合，但外部行为必须等价：

- 点击确认后立即锁定确认按钮；
- 同一对象、同一动作在请求完成前不能再次提交；
- 取消/关闭按钮按风险和状态禁用；
- 成功后先更新/刷新对象状态，再关闭浮层或展示成功结果；
- 失败保留表单输入和对象上下文；
- 组件卸载或列表刷新不能导致旧请求再次作用于新对象。

不要求本期把所有 mutation 抽象为全局状态机。优先抽出最小的高风险动作 composable/组件，避免过度泛化。

### 4.6 成功、失败、冲突、未知结果

统一采用以下最小语义：

| 结果 | 识别方式 | UI 行为 |
| --- | --- | --- |
| success | API 明确返回业务成功 | 展示对象名称、实际生效状态和下一步；刷新对应列表/详情 |
| failed | 校验、权限、服务等明确失败 | 保留输入和上下文；指出修复动作；允许重试或取消 |
| conflict | HTTP 409、版本冲突、状态已被他人改变 | 不重复写入；刷新最新对象；告知“当前操作未继续/已被他人处理” |
| unknown | 超时、断网或服务端无法证明最终结果 | 不显示为确定失败；优先使用现有结果查询/幂等键确认；确认前禁止第二次写入 |

建议为高风险动作增加轻量转换函数，而不是一开始重写所有 `handleApiError` 调用：

```ts
type MutationErrorKind =
  | 'validation'
  | 'permission'
  | 'network'
  | 'conflict'
  | 'server'
  | 'not_found'
```

当前 `CRM-Client/src/utils/errorHandler.ts` 已有网络、服务器、认证、业务、数据契约和未知错误，但 409 还没有独立分类。高风险动作应优先补充稳定分类；业务代码不能依赖中文错误文案做分支判断。

## 5. 高风险操作矩阵

> “是否增加确认步骤”描述的是相对于当前正常路径是否新增一个确认层，不代表不显示业务信息。已经存在的业务 Dialog 只做内部增强，不再叠加第二层。

| 操作 | 当前入口/承载 | 目标承载 | 是否增加步骤 | 确认/复核内容 | 成功后动作 | 失败/冲突/恢复 |
| --- | --- | --- | --- | --- | --- | --- |
| 客户领取 | 列表操作 + 全局 confirm | AlertDialog 或详情内轻量确认 | 否，保留一次确认 | 客户名、当前公海状态、领取后负责人 | 显示客户名和负责人，刷新列表 | 409 提示已被领取并刷新；无通用撤销，人工重新分配 |
| 客户退回公海 | Customers 自定义 modal | Dialog | 否，保留理由填写 | 客户名、当前负责人、目标公海状态、解除绑定、通知影响、退回理由 | 显示客户名、已退回公海，刷新列表/详情 | 保留理由；权限/状态冲突在 Dialog 内修复或刷新；人工重新领取/分配 |
| 客户移交 | `CustomerTransferDialog` | 业务 Dialog 增强 | 否 | 新负责人、移交范围、商机/合同影响、备注 | 展示客户、新负责人、实际移交商机/合同数 | 保留选择；409 刷新客户；人工重新移交 |
| 客户赢单 | 全局 confirm | AlertDialog | 否，保留一次确认 | 客户名、当前状态、目标赢单、通知影响 | 展示最终状态，刷新列表 | 409/状态失败刷新；必要时由业务管理员纠正 |
| 客户输单 | Customers 自定义 modal | Dialog | 否，保留理由填写 | 客户名、当前状态、目标输单、输单原因、通知影响 | 展示最终输单状态，刷新列表 | 理由字段错误聚焦；重复输单不清空输入；状态冲突刷新 |
| 客户失效 | 全局 confirm | AlertDialog | 否，保留一次确认 | 客户名、当前状态、目标失效、后续可用动作 | 显示最终状态，刷新列表 | 权限/状态失败刷新；人工恢复 |
| 客户删除 | `confirmDelete` | AlertDialog | 否，保留一次确认 | 客户名、逻辑删除语义、关联投影/数据影响、不可恢复说明 | 显示客户名和删除状态，刷新列表 | 权限/冲突保留上下文；无自动撤销，提供人工恢复入口 |
| 商机删除/输单 | 普通 confirm/页面私有逻辑 | AlertDialog 或理由 Dialog | 不新增确认层 | 商机名称、当前状态、关联客户/合同影响；输单时理由 | 刷新商机和关联上下文 | 409 刷新；失败保留理由；按业务恢复 |
| 合同删除 | `confirmDelete` | AlertDialog | 否，保留一次确认 | 合同名、草稿限制、关联回款计划将被清理、不可恢复 | 刷新合同列表和回款计划视图 | 状态/审批冲突不重试写入；人工恢复/重建 |
| 合同提交审批 | 页面提交动作 | 业务 Dialog 或直接提交 | 不默认增加 | 合同关键字段、审批影响、当前版本 | 展示审批实例/待审批状态 | 冲突刷新合同；审批流不存在时提示配置问题 |
| 发票申请撤回 | 审批组件 AlertDialog/页面动作 | AlertDialog | 否，保留一次确认 | 发票申请、当前审批状态、撤回后可编辑状态、通知影响 | 刷新详情/列表，展示已撤回 | 409 刷新审批状态；无通用撤销，重新提交 |
| 发票申请删除 | 列表/详情不同实现 | AlertDialog | 否，保留一次确认 | 申请编号、当前状态、关联业务影响、不可恢复 | 列表局部移除，详情按现有策略关闭并刷新 | 失败保留详情上下文；状态冲突刷新 |
| 发票冲红 | `InvoiceDetailSheet` 表单 Dialog | 现有 Dialog 规范化 | 否 | 原蓝字发票、冲红后状态、原因、红字号码、红字文件 | 刷新详情，显示已冲红及文件 | 文件/字段错误定位；提交失败保留表单；未知结果需查询最终状态 |
| 回款计划删除 | 普通 confirm | AlertDialog | 否，保留一次确认 | 计划名、当前状态、关联回款记录限制、不可恢复 | 刷新计划和合同汇总 | 有关联记录时明确不可删除；冲突刷新 |
| 回款登记 | 业务登记 Dialog | 现有 Dialog 规范化 | 否 | 客户/合同/计划、金额、日期、剩余可收金额、审批影响 | 使用返回状态更新计划/合同；显示回款编号 | 使用原幂等键查询结果；未知时不能重新登记 |
| 回款记录修改 | 详情/表单 Dialog | 现有业务 Dialog | 否 | 记录、金额/日期变化、计划/合同重算影响、当前版本 | 刷新记录、计划和合同状态 | 409 刷新版本；审批中/通过后按后端规则禁用 |
| 回款记录删除 | 普通 confirm | AlertDialog | 否，保留一次确认 | 记录、金额、计划/合同状态重算、不可恢复 | 刷新记录、计划和合同汇总 | 审批中/通过后拒绝；失败保留上下文 |
| 审批提交 | 详情/业务页面提交按钮 | 直接提交或轻量确认 | 不默认增加 | 页面已充分展示对象时直接提交；列表场景可轻量确认 | 展示审批实例和待审批状态 | 审批流配置/状态冲突明确提示 |
| 审批同意 | 详情按钮/移动快速操作 | 详情直接提交；移动快速操作 AlertDialog | 详情否，移动端保留一次轻确认 | 对象类型、名称、当前节点、同意后状态；移动端防误触 | 列表移除/详情更新为通过 | 409 刷新并提示已被处理；失败不重复提交 |
| 审批驳回 | 理由 Dialog | 统一业务 Dialog | 否，保留理由填写 | 对象、当前节点、必填驳回理由、提交人后续动作 | 展示已驳回及可重新提交 | 理由保留；409 刷新；失败可重试 |
| 审批撤回 | AlertDialog | AlertDialog 统一化 | 否，保留一次确认 | 对象、当前审批状态、撤回后状态、通知影响 | 展示已撤回，刷新详情 | 409 刷新；人工/重新提交 |
| 批量审批 | 已有批量 Dialog | 现有 Dialog 增强 | 否 | 业务类型、真实选中数量、动作、驳回理由要求、部分成功规则 | 成功/失败/他人已处理分组；失败项可重试 | 重试只针对失败项，不依赖筛选/分页；不重复成功项 |

## 6. 技术方案

### 6.1 高风险动作上下文模型

新增能力建议使用有限、结构化的上下文模型：

```ts
interface RiskActionContext {
  action: string
  objectType: string
  objectId: string | number
  objectName: string
  currentState?: string
  targetState?: string
  impactSummary?: string[]
  reason?: {
    required: boolean
    maxLength?: number
    placeholder?: string
  }
  trigger?: 'list' | 'detail' | 'sheet' | 'mobile' | 'bulk'
}
```

要求：

- `objectName` 只用于展示，不能作为写入主键；
- `objectId` 和业务类型必须在请求前再次校验，避免异步期间对象切换；
- `currentState` 和 `targetState` 用于解释，不替代后端状态校验；
- `impactSummary` 由业务调用点提供，不能由通用组件猜测；
- 批量操作使用数量和业务类型，不能把审批行 ID 当业务对象 ID；
- 未提供关键上下文时，组件应显示通用安全文案，但不能伪造影响范围。

### 6.2 通用高风险动作组件

建议新增：

```text
CRM-Client/src/components/crmwolf/HighRiskActionDialog.vue
CRM-Client/src/composables/useHighRiskAction.ts
```

组件职责：

- 渲染标题、对象上下文、状态变化、影响摘要；
- 可选渲染理由字段和字段错误；
- 提供确认、取消、重试、刷新/查询结果等事件；
- 管理 submitting/failed/conflict/unknown 的显示语义；
- 通过 `Dialog` 或 `AlertDialog` 的组合方式支持两类场景；
- 不负责调用业务 API，不负责路由，不推断业务状态。

不建议将所有调用点强行改成一个“万能弹窗”。更合理的边界是：

- `HighRiskActionDialog` 负责一次确认/结构化上下文；
- 各业务 Dialog 负责自身表单字段和业务提交；
- `useHighRiskAction` 负责最小的调用状态、错误归类和结果回调；
- 后端 API/Store 继续负责权限、状态机、幂等和版本冲突。

### 6.3 confirmDialog 兼容迁移

`CRM-Client/src/utils/confirmDialog.ts` 保留现有 `confirmDialog(message, title, options)` 作为兼容入口，新增结构化调用，例如：

```ts
interface RiskConfirmOptions extends RiskActionContext {
  title?: string
  confirmText?: string
  cancelText?: string
  variant?: 'default' | 'destructive'
}
```

迁移顺序：

1. 先修正 `confirmDialogImpl` 的并发行为：同一时间只允许一个全局确认，或使用队列并确保每个 Promise 都有明确完成结果；禁止静默覆盖 `resolve`。
2. 迁移 Customers 的退回公海/输单到业务 `Dialog`，不再依赖全局 confirm。
3. 迁移高频删除操作，优先补齐业务影响摘要和成功结果。
4. 迁移审批撤回和移动端快速审批。
5. 保留低风险或暂未迁移调用点的旧函数，减少大范围一次性改动。

### 6.4 表单理由与字段错误

需要理由的操作统一规则：

- 使用语义 `Label`，字段必须有稳定 `id`；
- 必填、最大长度和空白字符串校验在提交前执行；
- 错误放在字段附近，并使用 `role="alert"` 或等价实时语义；
- 错误发生后焦点移动到首个待处理字段；
- API 返回校验失败时保留原输入；
- 关闭有未保存内容的 Dialog 时询问是否放弃；
- 输单、退回公海、驳回等理由规则分别由业务调用点声明，不由通用组件硬编码。

### 6.5 删除与状态变更的 API 复用

原则上继续调用现有 API：

- 客户：`/customers/{id}`、`/customers/{id}/status`、`/customers/{id}/lose`、`/customers/{id}/return-to-pool`、`/customers/{id}/assign`；
- 合同：`DELETE /contracts/{id}`；
- 回款：现有计划/记录删除、更新和 `/payment-records/resolve`；
- 发票：现有申请删除、撤回和冲红接口；
- 审批：现有通用审批 Store/API 和实体状态查询。

前端不应为了显示确认摘要而先发起额外的写请求。若需要关联数量或状态，优先使用当前列表/详情响应已有字段；缺少关键字段时再评估增加只读 summary 接口。

### 6.6 统一错误转换

建议在 `CRM-Client/src/utils/errorHandler.ts` 增加高风险动作专用的轻量函数，例如：

```ts
interface MutationErrorResult {
  kind: MutationErrorKind
  title: string
  description: string
  retryable: boolean
  requiresRefresh: boolean
  outcome: 'failed' | 'conflict' | 'unknown'
}
```

第一阶段只覆盖：

- 400/422：校验或业务状态不允许；
- 401/403：未登录/无权限；
- 404：对象已不存在或当前上下文过期；
- 409：并发/版本/状态冲突；
- 无响应、超时：结果未知；
- 500/503：服务失败，可在确认未写入后重试。

不要求本期一次性改造全项目所有错误调用点。高风险动作可显式调用转换函数，其他页面保持兼容。

### 6.7 回款幂等与未知结果

回款登记必须复用现有实现：

- 前端只生成一次 `Idempotency-Key`；
- 网络超时/无响应后使用原 key 查询 `/payment-records/resolve`；
- 查询结果未确认时显示“正在确认结果”，不显示确定失败；
- 未证明未落库前，不允许生成第二个 key 再次登记；
- 后端已有重复 key replay 和 fingerprint 冲突逻辑，本期不另造前端操作 ID；
- 若某类高风险写接口没有可靠结果查询，先记录为后端补契约候选，不用 Toast 掩盖不确定性。

### 6.8 业务型 Dialog 的最小增强

#### CustomerTransferDialog

保留现有表单和 `submitting`，增加：

- 客户当前负责人和目标负责人摘要；
- 三种移交范围的影响说明；
- 选择范围后展示“预计影响对象”信息；
- 关闭保护和提交中关闭禁用；
- 成功展示客户、目标负责人、实际移交商机数/合同数。

不增加第二次确认。

#### InvoiceDetailSheet 冲红 Dialog

保留现有原因、红字号码和文件上传，增加：

- 原发票号码/状态/金额摘要；
- 冲红后状态说明；
- 字段级校验和错误聚焦；
- 提交中保持表单上下文；
- 成功后刷新详情并显示最终状态；
- 未知结果走查询，不盲目重试。

不增加第二次确认。

#### 回款登记 Dialog

保留已有金额校验、幂等键和结果确认。统一补充：

- 客户/合同/计划上下文；
- 操作后剩余金额和审批状态；
- 重复点击互斥；
- 结果未知时的查询动作；
- 成功后计划和合同状态刷新。

## 7. 前端文件改造清单

### 7.1 第一批必改

```text
CRM-Client/src/views/Customers.vue
CRM-Client/src/components/crmwolf/ConfirmDialog.vue
CRM-Client/src/utils/confirmDialog.ts
CRM-Client/src/utils/confirmDialogImpl.ts
```

建议新增：

```text
CRM-Client/src/components/crmwolf/HighRiskActionDialog.vue
CRM-Client/src/composables/useHighRiskAction.ts
```

### 7.2 第二批高频删除

```text
CRM-Client/src/views/Invoices.vue
CRM-Client/src/views/InvoiceDetailSheet.vue
CRM-Client/src/views/Contracts.vue
CRM-Client/src/views/PaymentPlans.vue
CRM-Client/src/views/PaymentRecords.vue
CRM-Client/src/views/Opportunities.vue
CRM-Client/src/components/FollowUpList.vue
CRM-Client/src/utils/errorHandler.ts
```

实际迁移必须按调用点逐个确认后端语义，禁止简单批量替换 `confirmDelete` 文案。

### 7.3 第三批审批

```text
CRM-Client/src/components/ApprovalProcessGeneric.vue
CRM-Client/src/views/ApprovalCenter.vue
CRM-Client/src/stores/approval.ts
```

复用 P1-PKG-02 已完成的 loading、错误、部分成功和重试能力，不另起一套反馈框架。

### 7.4 相关后端核查文件

```text
CRM-Server/app/api/customers.py
CRM-Server/app/api/contracts.py
CRM-Server/app/api/payments.py
CRM-Server/app/api/invoices.py
CRM-Server/app/api/approvals.py
```

本期默认只做契约核查和必要的错误码/只读查询补充，不改变已有状态限制。

## 8. 分批实施与独立验收

### Batch 1：Customers 临时 modal 迁移

覆盖：退回公海、标记输单、理由校验、提交互斥、失败保留、移动端、焦点/Escape、详情/列表可发现性。

独立验收：

- 两个临时 `div.modal-overlay` 删除；
- 使用设计系统 Dialog；
- 遮罩/Escape/取消不会提交；
- 非空理由关闭时有未保存保护；
- 重复点击只产生一次请求；
- API 失败后理由仍保留，错误可定位；
- 375px 和 390px 视口无页面横向溢出；
- 操作成功后列表和详情状态一致。

### Batch 2：高频删除统一

覆盖：客户、合同、发票申请、回款计划、回款记录、商机等。

独立验收：

- 每种删除确认内容与后端真实影响一致；
- 合同删除明确关联回款计划会清理；
- 回款计划/记录的状态限制在确认前或失败时可理解；
- 成功反馈包含对象和最终状态；
- 失败/409 不丢失对象上下文；
- 列表和详情删除行为一致或有明确差异说明；
- 没有把所有删除统一成同一句泛化文案。

### Batch 3：审批动作统一

覆盖：提交、同意、驳回、撤回、批量审批、移动快速审批。

独立验收：

- 详情同意正常路径不被强制增加无必要确认；
- 驳回理由必填、最大长度和错误聚焦一致；
- 撤回使用统一 AlertDialog，显示对象与状态；
- 409 后刷新详情并提示已被他人处理；
- 批量操作显示真实业务类型和数量；
- 部分成功结果不清空失败项，失败项可独立重试；
- 重试不会再次处理已经成功的对象。

### Batch 4：已有业务型 Dialog 规范化

覆盖：客户移交、发票冲红、回款登记及其他已具备表单复核的高风险 Dialog。

独立验收：

- 不新增二次确认层；
- 关键对象、金额、日期、范围和目标状态在同一浮层可复核；
- 提交中不可重复提交；
- 失败保留输入；
- 未知结果使用原有幂等/查询机制；
- 成功后刷新最终状态及关联汇总。

### Batch 5：全量回归与可访问性

覆盖：键盘、Escape、焦点恢复、读屏、移动端、减少动效、网络失败、409、权限不足、结果未知。

独立验收：

- 所有本包浮层有语义标题/描述；
- 图标按钮有可读名称；
- 焦点环可见，对比度符合设计系统；
- 错误后焦点进入首个待处理字段；
- 375/390/768/1280 等视口无页面横向溢出；
- `prefers-reduced-motion` 下不依赖动效传达状态；
- 遮罩点击不造成误提交或静默丢失。

## 9. 测试方案

### 9.1 单元测试

至少覆盖：

- `confirmDialogImpl` 并发调用不会悬挂 Promise 或错误归属；
- 取消、Escape 和关闭保护返回明确结果；
- 高风险动作上下文渲染对象、状态和影响摘要；
- 理由为空、超长、仅空白时阻止提交；
- submitting 时确认/取消/关闭按钮状态正确；
- 409 映射为 conflict；
- 网络超时映射为 unknown；
- 结果未知不生成第二个写请求；
- 批量重试只发送失败项。

### 9.2 页面/组件测试

优先新增或扩展：

```text
CRM-Client/src/components/crmwolf/__tests__/HighRiskActionDialog.test.ts
CRM-Client/src/utils/__tests__/confirmDialogImpl.test.ts
CRM-Client/tests/views/Customers.spec.ts
CRM-Client/tests/components/ApprovalProcessGeneric.spec.ts
CRM-Client/tests/views/ApprovalCenter.spec.ts
```

测试行为而非私有实现：

- 从可见入口打开动作；
- 看到正确对象和影响；
- 完成/取消/错误修复；
- API 调用次数和参数正确；
- 成功后的最终 UI 状态正确。

### 9.3 联调与异常注入

需要验证：

- 后端 400/403/404/409/500；
- 超时和断网；
- 同一对象双击/多窗口并发；
- 其他用户先修改状态；
- 审批已被他人处理；
- 回款登记服务端已成功但响应丢失；
- 移交范围导致多个商机/合同同步变化；
- 合同删除清理回款计划后的列表和详情一致性。

MySQL 本地连接按项目约定使用 **3307** 端口；本 TRD 不要求新增数据库结构，涉及联调时不得切换为默认 3306。

## 10. 可观测性与审计

本期不新增独立审计系统，但前端日志和后端已有审计应能关联以下最小信息：

- 操作类型；
- 资源类型和资源 ID；
- 操作前状态/目标状态（若适用）；
- 是否批量及数量；
- 结果类型：success/failed/conflict/unknown；
- 是否发生重试或结果查询；
- 审批实例 ID、版本或更新时间（若适用）。

日志不得记录完整理由、身份证件、发票附件内容或其他敏感业务数据。前端日志只记录可定位问题所需的脱敏上下文。

## 11. 回滚方案

### 11.1 前端回滚

- 每个 Batch 独立提交，不把 Customers、删除、审批和业务型 Dialog 放进同一个不可回滚发布单元；
- 保留旧 `confirmDialog` 兼容入口，迁移失败时可回退调用点；
- 新增组件只由已迁移页面引用，未迁移页面不受影响；
- 若统一错误转换出现兼容问题，恢复高风险调用点使用现有 `handleApiError`，保留组件迁移；
- 发布前保留旧样式/旧入口的可恢复 commit，但不在运行时同时展示两套浮层。

### 11.2 后端回滚

- 默认不改业务 API 和数据库，因此优先通过前端回滚；
- 如补充错误码或只读查询，必须向后兼容旧 `detail` 文案和旧响应字段；
- 不删除现有回款结果确认接口；
- 不回滚已有幂等键、审批冲突和审计逻辑；
- 若新增接口上线异常，前端降级为当前已有对象详情/列表刷新，不重复提交写操作。

## 12. 发布门禁

满足以下条件后才可认为本包完成：

- [ ] PRD 范围内第一批高风险操作完成统一承载；
- [ ] Customers 临时 modal 已移除；
- [ ] confirmDialog 并发覆盖风险已消除或明确拒绝并发且 Promise 有结果；
- [ ] 删除和状态变更确认文案经过业务逐项核对；
- [ ] P1-PKG-02 的 loading、错误、部分成功和重试能力被复用；
- [ ] 所有高风险动作有成功、失败、冲突或未知结果策略；
- [ ] 回款结果未知不发生盲目二次写入；
- [ ] 键盘、读屏、Escape、焦点恢复和移动端验收通过；
- [ ] 前端 `npm run type-check`、`npm run build`、相关单元测试通过；
- [ ] 后端若有改动，`ruff`、`mypy`、相关 `pytest` 和 Alembic 检查通过；
- [ ] 未引入 Agent / AI 自动化改动；
- [ ] 未增加无必要的正常路径确认步骤。

## 13. 最终产品与技术判断

1. **会不会拉长用户操作路径？**
   - 不会全面拉长。业务型 Dialog 不增加第二层确认；详情审批同意不强制增加确认；只有纯删除、撤回和移动端快速审批保留一次必要确认。

2. **会不会影响现有流程？**
   - 不改变后端业务状态机、权限、审批流、通知和回款幂等逻辑。前端主要改变浮层承载、文案、状态反馈和异常恢复。分批迁移可降低影响面。

3. **会不会出现过度优化？**
   - 按本 TRD 的边界不会。方案明确不做全量弹窗重写、不做通用撤销系统、不把普通操作全部变成 destructive、不增加确认页、不重新设计页面 IA，也不触碰 Agent / AI。

4. **最优先的技术动作是什么？**
   - 先迁移 Customers 的两个临时 modal，并修复全局 confirmDialog 的并发语义；再按删除、审批、业务型 Dialog 的顺序渐进迁移。
