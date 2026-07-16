# 合同、回款计划、发票与审批统一 DetailSheet 设计规格

**日期：** 2026-07-14  
**状态：** 待实施  
**范围：** 合同、回款计划、发票、审批中心详情交互  
**设计系统入口：** `CRM-Docs/design-system/README.md`

## 1. 背景

现有合同、回款计划和发票列表已经采用 `DataTable + FilterPanel + TopBar/headerStore`，但查看详情仍跳转到独立路由页面：

- `/contracts/:id`
- `/payments/plans/:id`
- `/invoices/:id`

这与原迁移计划的 DetailSheet 架构要求不一致，也与当前线索管理的列表内详情模式不一致。审批中心已经使用列表内 Sheet，但组件接口、布局、焦点回归和其他三个模块尚未统一。

本次重构将停止独立详情页导航，统一为“列表保持在原位，右侧打开 DetailSheet”。旧详情路由直接删除，不提供重定向或历史链接兼容。

## 2. 目标

1. 合同、回款计划、发票和审批详情统一使用列表内 `DetailSheet`。
2. 点击详情后 URL 保持列表地址不变。
3. 列表选择状态和 Sheet 公共接口使用业务编号，不使用数据库 ID：
   - 合同：`contract_number`
   - 回款计划：`plan_number`
   - 发票：`application_number`
   - 审批：`application_number`
4. 父列表在内部维护当前页的“业务编号 → 数据库 ID”映射，继续调用现有 ID 详情 API，不新增后端查询端点。
5. 从旧详情页面提取业务内容组件，消除对 `route.params` 和 `headerStore` 的依赖。
6. 删除三个独立详情路由与旧详情页面。
7. 遵循 CRMWolf 设计系统的 Sheet、详情页、响应式和无障碍规范。

## 3. 非目标

- 不迁移客户、商机、线索之外的其他业务详情。
- 不新增按业务编号查询详情的后端端点。
- 不保留旧详情 URL 的重定向、兼容或自动打开 Sheet 行为。
- 不用 query 参数记录当前打开的详情。
- 不重构与详情迁移无关的业务流程。

## 4. 设计依据

### 4.1 设计系统优先级

遵循 `CRM-Docs/design-system/README.md`：

> 页面特有规则 > 交互模式 > 组件规则 > 基础规范。

主要规范：

- `CRM-Docs/design-system/components/modal-sheet.md`
- `CRM-Docs/design-system/patterns/detail-page.md`
- `CRM-Docs/design-system/foundations/accessibility.md`
- `CRM-Docs/design-system/foundations/responsive-mobile.md`
- `CRM-Docs/design-system/foundations/spacing-layout.md`

### 4.2 现有参考实现

主要参考当前主工作区：

- `CRM-Client/src/views/Leads.vue`
- `CRM-Client/src/views/LeadDetailSheet.vue`
- `CRM-Client/src/components/ui/detail-sheet/DetailSheetContent.vue`
- `CRM-Client/src/views/ApprovalCenter.vue`

线索管理的核心模式：

```text
列表选择业务记录
→ 保存选择状态
→ 打开 Sheet
→ Sheet 按私有 ID 懒加载详情
→ 操作成功后刷新 Sheet 与列表
→ 关闭 Sheet
→ 清理选择状态并恢复触发元素焦点
```

## 5. 总体架构

每个模块拆分为三层。

```text
List View
├── DataTable / FilterPanel / TopBar
├── selectedBusinessNumber
├── selectedRecordId（仅父列表内部使用）
├── triggerElementRef
└── DetailSheet
    ├── Sheet / DetailSheetContent
    ├── Header / ScrollArea / Footer
    └── DetailContent
        ├── 详情 API
        ├── 业务状态
        └── 业务操作
```

### 5.1 列表页职责

列表页负责：

- 展示标准列表结构。
- 接收用户点击的业务编号。
- 从当前列表记录中解析数据库 ID。
- 保存触发详情的按钮或表格行元素。
- 打开对应 DetailSheet。
- 处理 Sheet 的 `refresh`、`deleted`、`closed` 等事件。
- 列表刷新后检查当前记录是否仍存在；不存在时关闭 Sheet 并提示。

列表页不得：

- 跳转到独立详情路由。
- 把数据库 ID 作为 Sheet 的用户可见标识。
- 在 URL query 中保存详情状态。

### 5.2 DetailSheet 职责

DetailSheet 负责：

- `Sheet`、`DetailSheetContent`、Portal 和 Overlay。
- Header、内部滚动区和 Footer。
- 加载骨架、错误状态和重新加载入口。
- 打开、关闭和焦点回归。
- 将私有加载 ID 传给 DetailContent。
- 将 DetailContent 事件转发给父列表。

DetailSheet 不依赖：

- `useRoute()` 或 `route.params`。
- `useRouter()` 的详情导航。
- `headerStore.setBack()` 或独立页面 TopBar 操作。

### 5.3 DetailContent 职责

DetailContent 负责：

- 按数据库 ID 加载详情数据。
- 格式化并展示业务信息。
- 编辑、审批、登记回款、标记开票等操作。
- 操作成功后刷新自身数据。
- 发出 typed 事件通知 Sheet 和父列表。

DetailContent 不负责：

- Sheet 宽度或 Portal。
- Sheet Header/Footer 外壳。
- 路由和 TopBar 状态。

## 6. 业务编号与私有 ID

### 6.1 公共接口

Sheet 对外使用业务编号：

```ts
interface ContractDetailSheetProps {
  visible: boolean
  contractNumber: string | null // 选择状态、标题与事件使用的公共业务标识
  recordId: number | null // 仅用于调用现有详情 API，不展示、不进入 URL
}

interface PaymentPlanDetailSheetProps {
  visible: boolean
  planNumber: string | null
  recordId: number | null
}

interface InvoiceDetailSheetProps {
  visible: boolean
  applicationNumber: string | null
  recordId: number | null
}

`recordId` 是父列表从当前记录解析出的内部加载参数。组件的选择、比较、标题、刷新定位和测试断言必须使用业务编号；数据库 ID 不得成为用户可见标识或跨组件业务事件的主键。
```

### 6.2 私有映射

父列表从当前行维护私有映射：

```ts
interface DetailSelection {
  businessNumber: string
  recordId: number
}
```

数据库 ID：

- 不展示在 Header。
- 不作为 Sheet 的用户选择值。
- 不进入 URL。
- 只用于调用当前已有详情 API。

父列表刷新后重新从列表数据解析映射，避免保存过期 ID。

## 7. 组件设计

### 7.1 合同

新增：

- `ContractDetailSheet.vue`
- `ContractDetailContent.vue`

修改：

- `Contracts.vue`

迁移来源：

- `ContractDetail.vue`

提取时必须同时移除 Element Plus 依赖，并使用 shadcn-vue/V2 组件完成等价业务能力；不得把旧页面的 `ElMessageBox`、loading directive、路由副作用或旧样式原样搬入 DetailContent。

Header 展示：

- 合同名称
- 合同编号 `contract_number`
- 合同状态
- 授权类型
- 合同总金额

Content 展示：

- 基本信息
- 回款计划
- 审批进度
- 关联客户与商机

Footer 根据权限和状态显示：

- 编辑
- 提交审批
- 撤回审批
- 审批操作

拒绝、确认等短任务使用 shadcn `Dialog` 或 `AlertDialog`。这些 Dialog 与 Sheet 作为页面级兄弟节点渲染，均通过 Portal 进入 `body`，不得把 Dialog DOM 嵌套在 Sheet 的可滚动内容中，以免焦点陷阱和层级冲突。

### 7.2 回款计划

新增：

- `PaymentPlanDetailSheet.vue`
- `PaymentPlanDetailContent.vue`

修改：

- `PaymentPlans.vue`

迁移来源：

- `PaymentPlanDetail.vue`

提取时同步迁移所有 Element Plus Card、Descriptions、Steps、Dialog 和通知调用；DetailContent 只使用 shadcn-vue、现有审批组件和 V2 tokens。

Header 展示：

- 回款计划编号 `plan_number`
- 关联合同
- 客户名称
- 阶段名称
- 当前状态
- 计划金额与已回款金额

Content 展示：

- 计划信息
- 回款进度
- 回款记录
- 审批信息
- 关联发票信息

Footer 根据状态显示：

- 编辑
- 登记回款
- 重新提交审批
- 查看合同

“查看合同”不跳转路由。父页面关闭当前回款计划 Sheet，并以关联合同编号打开 `ContractDetailSheet`。两个 Sheet 不同时打开，避免重叠焦点陷阱；合同 Sheet 关闭后焦点返回原回款列表中的触发元素。

### 7.3 发票

新增：

- `InvoiceDetailSheet.vue`
- `InvoiceDetailContent.vue`

修改：

- `Invoices.vue`

迁移来源：

- `InvoiceDetail.vue`

提取时同步移除剩余 Element Plus 标签、按钮和页面级路由依赖，保留 ISSUED 状态的已开票文件高亮区、文件下载反馈和审批信息。

Header 展示：

- 申请单号 `application_number`
- 客户与合同
- 发票类型
- 申请状态
- 开票金额

Content 展示：

- 申请信息
- 发票抬头
- 审批信息
- 发票文件
- 开票结果

Footer 根据权限和状态显示：

- 编辑
- 删除
- 标记开票
- 下载文件

标记开票必须使用 shadcn `Dialog`，不得继续使用自定义 Modal。

### 7.4 审批中心

修改：

- `ApprovalCenter.vue`
- 必要时提取 `ApprovalDetailSheet.vue`

保持：

- 列表内 Sheet 交互。
- `DataTable + FilterPanel + TopBar/headerStore`。
- 现有审批业务逻辑。

统一：

- 必须使用 `DetailSheetContent` 替代原始 `SheetContent`，桌面宽度统一为 75%、最大 1080px。
- 不额外提取 `ApprovalDetailSheet.vue`；直接统一 `ApprovalCenter.vue` 内现有 Sheet 结构。
- 选择状态使用 `business_type + application_number` 复合业务键，避免不同业务类型的相同编号发生碰撞。
- 私有加载状态继续保存 `business_type + business_id`，仅用于 `ApprovalProcessGeneric` 和现有详情 API。
- Header、ScrollArea、Footer 与其他 DetailSheet 一致。
- 关闭后的焦点回归。

## 8. Sheet 交互与生命周期

### 8.1 打开

```text
用户点击记录或“查看详情”
→ 保存业务编号、私有 ID 和触发元素
→ visible = true
→ Sheet 打开并将焦点移入浮层
→ Content 懒加载详情
```

DetailContent 仅在 `visible=true` 且业务编号、私有 ID 均有效时发起详情请求。Sheet 关闭时清空详情数据和内部表单状态，不在后台继续请求，也不保留上一个对象的 DOM 状态。

### 8.2 关闭

支持：

- 明确的关闭按钮。
- Escape。
- 业务操作成功后的程序化关闭。

不得只依赖点击遮罩关闭。

关闭完成后：

1. 清空业务编号。
2. 清空私有 ID。
3. 清空详情数据。
4. 将焦点返回触发按钮或表格行。

父列表在打开前保存 `triggerElement: HTMLElement | null`。关闭动画完成后，若该元素仍连接在 DOM 中则调用 `focus()`；若记录已删除或元素已卸载，则聚焦 DataTable 容器或列表标题，保证焦点不会落到 `body`。

### 8.3 刷新

业务操作成功后：

1. Content 刷新自身详情。
2. emit `refresh`。
3. 父列表刷新。
4. 父列表按业务编号重新解析当前记录。
5. 记录不存在时关闭 Sheet，并通过 `vue-sonner` 提示。

### 8.4 提交期间与未保存更改

**提交期间：**

- 禁止重复提交。
- 禁用会造成数据不确定的关闭操作。
- 不可逆操作使用 AlertDialog 说明影响。

**未保存数据的关闭行为：**

所有关闭路径：

- 点击关闭按钮
- 按 Escape
- 点击遮罩
- 跨模块切换到另一个 Sheet
- 业务操作要求程序化关闭

**关闭协议：**

```text
dirty = false
→ 直接关闭

dirty = true
→ 打开 AlertDialog
   ├── 继续编辑：关闭 AlertDialog，保留 Sheet 和输入
   └── 放弃更改：重置表单，再关闭 Sheet
```

**AlertDialog 文案：**

- 标题：有未保存的更改
- 描述：关闭后，当前尚未保存的内容将丢失。
- 取消按钮：继续编辑
- 破坏性操作：放弃更改

**提交进行中时：**

- 禁用关闭按钮。
- 禁用 Escape 和遮罩关闭。
- 禁止打开另一个业务 Sheet。
- 显示加载状态并防止重复提交。

### 8.5 跨模块 Sheet 切换

回款计划 Sheet 的"查看合同"已确定为打开合同 Sheet，切换顺序如下：

```text
PaymentPlanDetailSheet
→ 用户点击"查看合同"
→ 保存原始触发元素
→ 关闭 PaymentPlanDetailSheet
→ 等待关闭动画完成
→ 清理回款 Sheet 状态
→ 打开 ContractDetailSheet
→ 焦点进入合同 Sheet
→ 关闭合同 Sheet
→ 焦点返回原回款列表触发元素
```

**约束：**

- 同一时刻只能打开一个业务 DetailSheet。
- 不允许两个 Sheet 叠加。
- 不允许合同 Sheet 再打开回款 Sheet，形成循环。
- 跨 Sheet 切换期间 URL 仍保持 `/payments/plans`。
- 原始触发元素失效时，焦点回到 DataTable 容器。

**推荐状态管理：**

```ts
type ActiveDetailSheet =
  | { type: 'payment-plan'; number: string; recordId: number }
  | { type: 'contract'; number: string; recordId: number }
  | null
```

比维护多个独立的 `paymentSheetVisible`、`contractSheetVisible` 更安全。

## 9. 视觉结构

统一结构：

```vue
<Sheet>
  <DetailSheetContent>
    <SheetHeader />
    <ScrollArea class="flex-1">
      <DetailContent />
    </ScrollArea>
    <SheetFooter />
  </DetailSheetContent>
</Sheet>
```

### 9.1 宽度

所有业务详情 Sheet 必须使用现有 `DetailSheetContent`，宽度由该共享组件统一控制。

**当前组件契约：**

- 桌面端：右侧 `w-3/4`
- 最大宽度：`max-w-[1080px]`
- 窄视口：全宽

**约束：**

- 业务 Sheet 不得自行覆盖宽度。
- 宽度事实来源为 `DetailSheetContent.vue`，不在每个 Sheet 规格中重复定义。
- 后续可单独将该组件契约补入设计系统 `modal-sheet.md`，但不阻塞本次开发。

### 9.2 Sheet 内容复杂度边界

设计系统明确规定：

> 抽屉不应用作复杂多阶段流程或常规一级导航的替代。

**Sheet 适用场景：**

- 以只读详情展示为主。
- 允许单步操作：
  - 简单编辑（单表单、无向导）
  - 单次审批（同意/拒绝）
  - 登记回款（单条记录）
  - 标记开票
  - 下载文件

**不适用场景：**

- 创建向导（多步骤表单）
- 批量配置
- 复杂多步骤流程
- 需要跨模块一级导航的操作

**边界约束：**

- Sheet Footer 不承担跨模块一级导航。
- 内联编辑进入 dirty 状态时必须启用关闭确认。
- 内容长度由信息层级决定，不以固定数量（如"卡片不超过 5 个"或"只能滚动两屏"）人为限制。

### 9.3 Header

Header 按顺序展示：

1. 对象头像或业务图标。
2. 对象名称。
3. 业务编号。
4. 状态 Badge。
5. 一项关键摘要。

Header 不放置复杂表单或次要历史信息。

### 9.4 Content

- 使用 `ScrollArea` 独立滚动。
- 卡片间距使用 `$wolf-card-gap-v2`，即 16px。
- 卡片内边距使用 `$wolf-card-padding-v2`。
- 属性组桌面多列、平板两列、移动端单列。
- 嵌入表格仅在自身容器内横向滚动。

### 9.5 Footer

- 固定在 Sheet 底部。
- 只包含当前状态可执行的主要操作。
- 避开移动端安全区域。

**操作溢出规则：**

桌面端：

- 最多直接展示 3 个操作。
- 只允许 1 个 primary。
- 第 4 个及以后进入 DropdownMenu。

移动端：

- 最多直接展示 2 个操作。
- 其余进入"更多操作"菜单。
- 更多按钮 `aria-label="更多操作"`。
- 相邻触控目标间距至少 8px。

**危险操作：**

- 删除、拒绝、撤回等与普通操作使用 Separator 分隔。
- 使用 destructive 样式。
- 必须经过 AlertDialog 确认。
- Footer 不得因按钮数量换行成两层。

### 9.6 移动端验收条件

- `< 768px` 使用全宽 Sheet。
- Sheet Header 避开顶部安全区域。
- Footer 使用底部安全区域 padding。
- 背景页面锁定滚动。
- 只有 Sheet 的 ScrollArea 负责纵向滚动。
- 不产生页面级横向滚动。
- Footer 不遮挡最后一项内容。
- 移动端正文与表单输入不小于 16px，避免 iOS 自动缩放。
- 375px 和移动横屏均能完成全部操作。
- 不自行实现 swipe-to-close。继续使用 Reka/Sheet 的标准行为，避免与系统返回手势冲突。

### 9.7 Loading、错误与布局稳定性

**Loading 状态：**

- Sheet 一打开就渲染骨架结构，不能先空白再突然出现内容。
- 请求超过 300ms 时必须显示 Skeleton 或明确 loading。
- Skeleton 应模拟 Header、核心属性卡片和主要内容区域（不写死"最小高度 600px"，由各模块首屏结构决定）。
- 加载期间 Footer 操作禁用。

**错误状态：**

- ErrorState 必须提供：
  - 错误原因
  - 重新加载按钮
  - 关闭按钮
- ErrorState 使用 `role="alert"` 或适当实时区域。

**布局稳定性：**

- 内容替换不得造成明显宽度变化或 Header/Footer 跳动。
- 视觉回归目标：CLS < 0.1。

## 10. 无障碍

必须满足：

- Sheet 有 `SheetTitle` 和 `SheetDescription`。
- 打开后焦点进入 Sheet，并被限制在浮层内。
- 关闭后焦点返回触发元素。
- 所有交互目标至少 44×44。
- 图标按钮提供可读名称。
- 装饰图标设置 `aria-hidden="true"`。
- 键盘可使用 Tab、Shift+Tab、Enter、Space 和 Escape 完成全部操作。
- 焦点使用 V2 focus ring token。
- 动态成功和失败反馈使用 `vue-sonner`。
- 保留 shadcn/Reka 原生动画和焦点陷阱，不自定义过渡时长。

## 11. 路由与删除策略

删除路由：

- `/contracts/:id`
- `/payments/plans/:id`
- `/invoices/:id`

删除或替换旧页面：

- `ContractDetail.vue`
- `PaymentPlanDetail.vue`
- `InvoiceDetail.vue`

不提供：

- redirect
- alias
- query 深链
- 旧链接兼容

访问旧 URL 时沿用应用现有未匹配路由行为。

## 12. 错误处理

### 12.1 详情加载失败

- Sheet 保持打开。
- 显示 ErrorState。
- 提供“重新加载”按钮。
- 不把用户自动退回列表顶部。

### 12.2 列表刷新失败

- 保留 Sheet 当前内容。
- 使用 `vue-sonner` 提示列表刷新失败。

### 12.3 记录不存在

- 关闭 Sheet。
- 立即清空业务编号和私有 ID。
- 提示：“该记录已被删除或权限已变更”。
- 焦点回到 DataTable 容器或列表标题。

### 12.4 权限变化

- API 返回 403 时保留明确提示。
- 隐藏无权限操作。
- 不在前端伪造可用状态。

## 13. 测试与验收

### 13.1 组件测试

每个 DetailSheet 覆盖：

- 业务编号和标题渲染。
- visible 双向绑定。
- 打开时懒加载。
- 加载、成功、错误状态。
- 关闭清理。
- 焦点回归。
- refresh 事件。
- 操作按钮的权限与状态可见性。

每个 DetailContent 覆盖：

- API 加载。
- 操作成功刷新。
- 操作失败反馈。
- 提交期间防重复。

### 13.2 列表集成测试

- 点击业务名称和“查看详情”均打开 Sheet。
- URL 不变化。
- 选择状态使用业务编号。
- 私有 ID 不显示在 UI。
- Sheet 更新后列表刷新一次。
- 关闭后焦点回到触发元素。
- 列表刷新后记录不存在时关闭 Sheet。

### 13.3 路由测试

- 三个详情路由不存在。
- 列表路由正常工作。
- 旧 URL 进入现有 404/未匹配行为。

### 13.4 真实浏览器验收

桌面与移动端验证：

- 合同列表打开/关闭详情。
- 回款计划列表打开/关闭详情。
- 发票列表打开/关闭详情。
- ApprovalCenter 打开/关闭审批详情。
- Sheet 内滚动不推动背景页面。
- Escape、关闭按钮和焦点回归。
- 编辑、审批、登记回款、标记开票后的列表刷新。
- 375px、768px、1024px、1440px 视口无不可达内容或页面横向滚动。

### 13.5 验收测试清单

**焦点回归：**

- 打开 Sheet → 焦点进入 Sheet → Escape 关闭 → 焦点回到原按钮
- 删除当前记录 → Sheet 关闭 → 原按钮已不存在 → 焦点回到 DataTable

**跨 Sheet：**

- 打开回款计划 Sheet → 查看合同 → 回款 Sheet 完全关闭 → 合同 Sheet 才打开
- 任意时刻 DOM 中只有一个业务 Sheet

**Dirty 状态：**

- 修改表单 → Escape → 出现放弃确认 → 继续编辑后输入保留
- 再关闭并放弃 → 表单状态清空

**移动端：**

- 375px 全宽
- Footer 不被底部手势区域遮挡
- 背景列表不能滚动
- Sheet 内容可独立滚动
- 横屏可完成全部操作

**动效减少：**

- 启用 `prefers-reduced-motion: reduce` 后功能不受影响
- 不增加自定义动画
- Sheet 继续使用 shadcn/Reka 的 reduced-motion 行为

## 14. 实施顺序

1. 修正共享 `DetailSheetContent` 与焦点回归基础设施。
2. 提取合同 DetailContent，接入 ContractDetailSheet 和 Contracts.vue。
3. 提取回款计划 DetailContent，接入 PaymentPlanDetailSheet 和 PaymentPlans.vue。
4. 提取发票 DetailContent，接入 InvoiceDetailSheet 和 Invoices.vue。
5. 统一 ApprovalCenter 的 Sheet 接口与布局。
6. 删除旧详情路由和页面。
7. 执行组件、集成和真实浏览器回归。

## 15. 设计决策与权衡

### 15.1 前端编号映射而非新增后端端点

选择：列表和 Sheet 使用业务编号，父列表私有映射到数据库 ID。

优点：

- 不扩大后端范围。
- 不改变现有 API。
- 用户界面和组件接口不暴露数据库 ID。

代价：

- Sheet 只能从当前列表记录打开。
- 不支持通过业务编号深链直接打开。
- 列表刷新后必须重新解析映射。

### 15.2 删除详情路由而非保留兼容

选择：直接删除三个详情路由。

优点：

- 单一交互模式。
- 不维护页面和 Sheet 两套实现。
- 避免 route/headerStore 与 Sheet 生命周期耦合。

代价：

- 历史链接失效。
- 无法刷新并恢复打开的详情。

### 15.3 提取 Content 而非 Sheet 包裹旧页面

选择：提取业务内容组件。

优点：

- 组件职责清晰。
- 容易测试。
- 不继承旧页面的路由和 TopBar 副作用。

代价：

- 初始搬迁工作量高于直接嵌套旧页面。

### 15.4 UI/UX Pro Max 建议不采用内容

UI/UX Pro Max 提供了多项通用建议，但以下内容与项目设计系统冲突，不采用：

**不采用 1：Roboto 字体与新颜色方案**

UI/UX Pro Max 推荐了 Roboto 字体和一套蓝绿配色，但项目已有 V2 Token 和字体规范。

直接采用会形成第二套设计系统，违反设计系统优先级：

> 页面特有规则 > CRMWolf 交互模式 > CRMWolf 组件规则 > CRMWolf 基础规范 > UI/UX Pro Max 通用建议

因此继续以 CRMWolf V2 Token 为唯一来源，不引入 Roboto 或新颜色。

**不采用 2：强制 50 行以上虚拟化**

这属于过早优化。嵌入数据应先：

- 分页
- 限制默认加载量
- 独立滚动

只有运行验证证明大数据量产生性能问题时，再引入 `@tanstack/vue-virtual`。不能仅凭"超过 50 行"增加依赖。

**不采用 3：为旧 URL 新增 404 引导**

已明确决策：

- 删除旧详情路由
- 不做兼容处理
- 不处理旧链接

因此不在本规格中加入旧 URL 跳转或专用 404 文案。这是已确认的产品决策，与 UI/UX Pro Max 的通用建议无关。
