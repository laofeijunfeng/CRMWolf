# 客户详情 Sheet 内部商机详情下钻改造实施计划

> 日期：2026-07-15  
> 范围：CRM-Client 前端  
> 目标：将客户详情 Sheet 中“商机 tab → 商机详情”的交互改造成单层 Sheet 内部下钻，避免 Sheet 套 Sheet，并保留现有商机列表页的商机详情 Sheet 能力。

## 设计系统依据

本计划已对齐 CRMWolf 目标设计系统入口：

```text
CRM-Docs/design-system/README.md
```

实施时按设计系统优先级执行：

```text
页面特有规则 > 交互模式 > 组件规则 > 基础规范
```

本改造重点涉及以下规范文件：

```text
CRM-Docs/design-system/components/modal-sheet.md
CRM-Docs/design-system/components/list-card.md
CRM-Docs/design-system/components/tabs.md
CRM-Docs/design-system/components/button.md
CRM-Docs/design-system/components/card.md
CRM-Docs/design-system/patterns/detail-page.md
CRM-Docs/design-system/foundations/accessibility.md
CRM-Docs/design-system/foundations/responsive-mobile.md
CRM-Docs/design-system/foundations/spacing-layout.md
CRM-Docs/design-system/foundations/color-tokens.md
CRM-Docs/design-system/foundations/motion-performance.md
CRM-Docs/design-system/foundations/radius-elevation.md
```

如实现中新增样式、状态、交互或布局，必须优先查阅上述设计系统文件，而不是沿用旧 Element Plus 或旧 `variables.scss` 风格。

---

## 1. 背景与问题

当前客户详情中的商机查看路径大致为：

```text
客户列表
  → 打开客户详情 Sheet
    → 切换到商机 tab
      → 点击商机
        → 跳转到 /opportunities/:id 或进入独立商机详情能力
```

从用户旅程看，用户在客户详情 Sheet 中查看商机时，主上下文仍然是“客户”。商机只是客户详情下的关联对象。如果此时再打开一个商机详情 Sheet，会形成：

```text
客户详情 Sheet
  → 商机详情 Sheet
```

这种模式会带来以下问题：

1. 用户难以判断当前处于哪一层；
2. 关闭按钮语义混乱：是关闭商机，还是关闭客户详情；
3. Esc、遮罩点击、浏览器返回行为难以保持一致；
4. 多层 Sheet 会产生 focus trap、z-index、遮罩叠加问题；
5. 移动端尤其容易变成“浮层迷宫”；
6. 后续合同、回款、发票等关联对象也可能继续套 Sheet，形成不可持续交互模式。

因此，本次改造采用成熟 CRM / 企业 SaaS 更常见的模式：

> 客户详情 Sheet 保持单层；商机详情作为客户详情 Sheet 内部的下钻视图展示。

该结论也符合 `components/modal-sheet.md` 的使用边界：抽屉适合在保留页面参照时承载补充信息或较长任务，但不应用作长期页面、复杂多阶段流程或常规一级导航替代。因此商机详情不应再创建第二个抽屉，而应作为当前客户详情抽屉内的内容状态。

---

## 2. 改造目标

### 2.1 用户体验目标

改造后，目标用户路径为：

```text
客户列表
  → 客户详情 Sheet
    → 商机 tab
      → 商机列表
        → 点击商机
          → 当前客户详情 Sheet 内部进入商机详情
            → 点击“返回商机列表”
              → 回到商机 tab 的商机列表
```

核心体验要求：

1. 点击客户详情内的商机后，不跳出客户上下文；
2. 不打开第二层 Sheet；
3. 商机详情顶部有明确返回入口；
4. 返回后仍停留在客户详情 Sheet 的商机 tab；
5. 客户详情 Sheet 的关闭和内部返回语义分离；
6. 商机详情中仍可提供“打开完整商机详情”入口，用于深度处理。

### 2.2 技术目标

1. 抽出可复用的商机详情内容组件；
2. `OpportunityDetailSheet.vue` 变成薄壳，只负责 Sheet 容器；
3. `CustomerDetailSheet.vue` 在商机 tab 内复用商机详情内容组件；
4. `OpportunitiesPanel.vue` 不再强制路由跳转，而是 emit 选择事件；
5. 保留 `/opportunities` 商机列表页现有打开 `OpportunityDetailSheet` 的能力；
6. 商机详情操作后可以刷新客户详情中的商机、合同、客户摘要等相关数据；
7. 为后续 URL query 深链和浏览器 Back 行为预留架构空间。

---

## 3. 当前实现概览

基于当前代码结构，相关文件如下：

```text
CRM-Client/src/views/Customers.vue
CRM-Client/src/views/CustomerDetailSheet.vue
CRM-Client/src/components/panels/OpportunitiesPanel.vue
CRM-Client/src/views/Opportunities.vue
CRM-Client/src/views/OpportunityDetailSheet.vue
CRM-Client/src/views/OpportunityDetail.vue
CRM-Client/src/components/ui/detail-sheet/DetailSheetContent.vue
CRM-Client/src/components/crmwolf/ListCard.vue
CRM-Client/src/components/crmwolf/ContextTabs.vue
CRM-Client/src/router/index.ts
```

### 3.1 客户列表到客户详情

```text
Customers.vue
  → selectedCustomerId
  → sheetVisible
  → CustomerDetailSheet.vue
```

客户详情 Sheet 的打开状态目前由 `Customers.vue` 本地状态控制，不是路由状态。

### 3.2 客户详情 Sheet 内部 tabs

`CustomerDetailSheet.vue` 内部通过本地状态管理 tab，例如：

```text
follow-up
contacts
opportunities
contracts
payments
invoices
license
```

商机 tab 当前渲染：

```text
OpportunitiesPanel.vue
```

### 3.3 客户详情商机列表点击行为

当前 `OpportunitiesPanel.vue` 更偏向直接跳转完整商机详情：

```text
点击商机相关入口
  → router.push('/opportunities/:id')
```

这会导致用户离开客户详情 Sheet 上下文。

### 3.4 商机列表页的详情 Sheet

另一个路径是：

```text
Opportunities.vue
  → 点击商机
  → OpportunityDetailSheet.vue
```

`OpportunityDetailSheet.vue` 当前同时承担两个职责：

1. Sheet 外壳；
2. 商机详情内容、数据加载、动作处理。

因此它不能直接嵌入 `CustomerDetailSheet.vue`，否则会造成 Sheet 套 Sheet。

---

## 4. 目标架构

### 4.1 改造前

```text
CustomerDetailSheet.vue
  └─ OpportunitiesPanel.vue
       └─ router.push('/opportunities/:id')

Opportunities.vue
  └─ OpportunityDetailSheet.vue
       ├─ Sheet 外壳
       └─ 商机详情内容
```

### 4.2 改造后

```text
CustomerDetailSheet.vue
  └─ OpportunitiesPanel.vue
  └─ OpportunityDetailContent.vue

OpportunityDetailSheet.vue
  └─ OpportunityDetailContent.vue
```

### 4.3 核心组件职责

#### `OpportunityDetailContent.vue`

新增可复用内容组件。

负责：

1. 加载商机详情；
2. 展示商机详情内容；
3. 展示关联合同信息；
4. 发起或承载赢单、输单、编辑、创建合同、查看合同等动作入口；
5. 通过 emits 通知外层返回、关闭、刷新、跳转完整页等。

不负责：

1. 不包含 `<Sheet>`；
2. 不包含 `<SheetContent>`；
3. 不管理外层浮层 open/close；
4. 不假设自己一定处于 Sheet 中。

#### `OpportunityDetailSheet.vue`

改造成薄壳。

负责：

1. Sheet open/close；
2. `DetailSheetContent` 容器；
3. 将 `opportunityId` 传给 `OpportunityDetailContent.vue`；
4. 将内容组件的 emits 映射回原有商机列表页行为。

#### `CustomerDetailSheet.vue`

负责：

1. 客户详情 Sheet 容器；
2. 内部 tab 状态；
3. 商机 tab 的列表/详情下钻状态；
4. 从商机详情返回商机列表；
5. 商机动作成功后刷新客户相关数据。

#### `OpportunitiesPanel.vue`

负责：

1. 展示客户下的商机列表；
2. 点击商机时 emit 内部下钻事件；
3. 可选提供“打开完整详情页”事件。

---

## 5. 文件级改造计划

### 5.0 设计系统对齐要求

本阶段不只做代码拆分，还必须同步遵守设计系统组件契约：

1. Sheet / 抽屉边界遵循 `components/modal-sheet.md`：
   - 一个任务路径只保留一层 Sheet；
   - Sheet 必须有明确标题、关闭方式和任务结果；
   - 打开后焦点进入 Sheet，关闭后焦点回到启动元素；
   - 不得只依赖点击遮罩关闭；
   - 内容内部滚动，不导致页面背景横向滚动。
2. 商机列表遵循 `components/list-card.md`：
   - Sheet 内实体列表优先使用列表卡片；
   - 列表项最小高度 44px；
   - 可点击项必须键盘可达并显示焦点；
   - 行点击与行内按钮不得产生点击目标冲突；
   - 无数据、加载、失败状态必须有明确状态和后续动作。
3. 客户详情 tabs 遵循 `components/tabs.md`：
   - tabs 只用于同一客户上下文中的并列内容视图；
   - 不能用 tabs 表达下钻步骤；
   - 切换 tab 不得静默丢弃未保存输入；
   - 窄视口下 tabs 可在标签栏内滚动，但不得导致页面整体横向滚动。
4. 商机详情内容遵循 `patterns/detail-page.md`：
   - 顶部为对象标识与主要操作；
   - 中部为核心属性组与关联内容；
   - 低频属性进入可展开区域；
   - 展示区不直接混用复杂编辑状态，编辑通过按钮触发。
5. 新增按钮遵循 `components/button.md`：
   - 每个任务区域只保留一个主操作；
   - 纯导航使用链接或文本按钮语义，不伪装成主按钮；
   - 图标按钮必须有可读名称；
   - 危险操作必须使用危险语义并在不可逆时确认。
6. 新增卡片/属性分组遵循 `components/card.md`：
   - 只为独立可理解内容组使用卡片；
   - 不用装饰性卡片堆叠制造层级；
   - 可激活卡片必须键盘可达并显示焦点。

## 5.1 新增：`CRM-Client/src/components/panels/OpportunityDetailContent.vue`

### 职责

该组件作为商机详情的唯一内容来源，被以下场景复用：

```text
OpportunityDetailSheet.vue
CustomerDetailSheet.vue 的商机内部下钻
```

### 建议 props

```ts
interface CustomerContext {
  customerId: number
  customerName?: string
}

interface Props {
  opportunityId: number
  embedded?: boolean
  customerContext?: CustomerContext | null
}
```

说明：

- `opportunityId`：必传，当前商机 ID；
- `embedded`：是否嵌入在其他详情上下文中；
- `customerContext`：客户详情内嵌场景使用，展示来源客户并支持刷新语义。

### 建议 emits

```ts
interface Emits {
  (e: 'back'): void
  (e: 'close'): void
  (e: 'refresh'): void
  (e: 'open-full-page', opportunityId: number): void
  (e: 'edit', opportunityId: number): void
  (e: 'view-contract', contractId: number): void
  (e: 'create-contract', opportunityId: number): void
}
```

### Header 行为

独立 Sheet 场景：

```text
商机详情
商机名称
```

客户详情内嵌场景：

```text
← 返回商机列表
商机名称
客户：客户名称
```

### 交互要求

1. `embedded=true` 时显示“返回商机列表”；
2. `embedded=true` 时建议显示“打开完整商机详情”次级入口；
3. loading、empty、error 状态都在内容组件内处理；
4. 业务动作成功后 emit `refresh`；
5. 不直接关闭外层 Sheet，关闭意图通过 emit `close` 交给外层。

---

## 5.2 修改：`CRM-Client/src/views/OpportunityDetailSheet.vue`

### 改造目标

将该组件从“Sheet + 内容”改为“Sheet 壳 + `OpportunityDetailContent`”。

### 改造前职责

```text
OpportunityDetailSheet.vue
  ├─ 控制 Sheet open/close
  ├─ 加载商机详情
  ├─ 加载关联合同
  ├─ 展示详情内容
  ├─ 处理赢单/输单
  ├─ 处理编辑/合同跳转
  └─ 展示 footer actions
```

### 改造后职责

```text
OpportunityDetailSheet.vue
  ├─ 控制 Sheet open/close
  ├─ 渲染 DetailSheetContent
  ├─ 渲染 OpportunityDetailContent
  └─ 将 OpportunityDetailContent 事件映射到当前页面行为
```

### 伪代码结构

```vue
<template>
  <Sheet v-model:open="visible">
    <DetailSheetContent>
      <OpportunityDetailContent
        v-if="opportunityId"
        :opportunity-id="opportunityId"
        @close="visible = false"
        @refresh="handleRefresh"
        @edit="handleEdit"
        @view-contract="handleViewContract"
        @create-contract="handleCreateContract"
        @open-full-page="handleOpenFullPage"
      />
    </DetailSheetContent>
  </Sheet>
</template>
```

### 验收点

1. `/opportunities` 页面点击商机仍能打开详情 Sheet；
2. 原商机详情内容展示一致；
3. 原有编辑、赢单、输单、创建合同、查看合同等动作不回退；
4. 不改变 `OpportunityDetailSheet.vue` 对外主要 props/emits，降低影响范围。

---

## 5.3 修改：`CRM-Client/src/components/panels/OpportunitiesPanel.vue`

### 改造目标

从“自己决定跳转”改成“通知父级用户选择了某个商机”。

### 建议 emits

```ts
interface Emits {
  (e: 'view-opportunity', opportunityId: number): void
  (e: 'open-full-page', opportunityId: number): void
}
```

### 行为调整

#### 主行为：内部下钻

用户点击商机行：

```ts
emit('view-opportunity', opportunity.id)
```

#### 次级行为：打开完整详情

用户点击外链按钮或更多菜单中的“打开完整详情”：

```ts
emit('open-full-page', opportunity.id)
```

### UI 建议

商机列表行可以呈现为：

```text
[阶段] 商机名称                                      >
金额：¥320,000   预计成交：2026-08-30   负责人：张三
```

建议：

1. 整行可点击；
2. 使用 chevron 表达“进入下一级”；
3. 外链/打开完整页作为次级动作，不作为默认主点击；
4. 保留键盘可访问性和 focus ring；
5. 点击区域满足最小触控尺寸要求。

---

## 5.4 修改：`CRM-Client/src/views/CustomerDetailSheet.vue`

### 改造目标

在客户详情 Sheet 的商机 tab 中加入内部下钻状态。

### 推荐状态模型

为了后续合同、回款、发票等也支持类似下钻，建议不要只用 `selectedOpportunityId`，而是设计通用 drilldown 状态：

```ts
type DrilldownView =
  | { type: 'none' }
  | { type: 'opportunity'; id: number }

const drilldownView = ref<DrilldownView>({ type: 'none' })
```

后续可扩展为：

```ts
type DrilldownView =
  | { type: 'none' }
  | { type: 'opportunity'; id: number }
  | { type: 'contract'; id: number }
  | { type: 'payment'; id: number }
  | { type: 'invoice'; id: number }
```

### 进入商机详情

```ts
function handleViewOpportunity(opportunityId: number): void {
  drilldownView.value = {
    type: 'opportunity',
    id: opportunityId,
  }
}
```

### 返回商机列表

```ts
function backToOpportunityList(): void {
  drilldownView.value = { type: 'none' }
}
```

### 打开完整商机详情

```ts
function openOpportunityFullPage(opportunityId: number): void {
  router.push(`/opportunities/${opportunityId}`)
}
```

### 商机 tab 渲染逻辑

```vue
<OpportunitiesPanel
  v-if="activePanel === 'opportunities' && drilldownView.type === 'none'"
  :customer-id="customerId"
  :opportunities="opportunities"
  @view-opportunity="handleViewOpportunity"
  @open-full-page="openOpportunityFullPage"
/>

<OpportunityDetailContent
  v-if="activePanel === 'opportunities' && drilldownView.type === 'opportunity'"
  :opportunity-id="drilldownView.id"
  embedded
  :customer-context="{
    customerId,
    customerName: customer?.account_name,
  }"
  @back="backToOpportunityList"
  @refresh="refreshAfterOpportunityChange"
  @open-full-page="openOpportunityFullPage"
/>
```

### tab 切换行为

推荐第一版采用简单可预测规则：

```text
用户从商机详情切换到其他 tab
  → 自动退出当前下钻
  → 展示目标 tab
```

实现示例：

```ts
watch(activePanel, () => {
  drilldownView.value = { type: 'none' }
})
```

注意：如果后续商机详情内支持未保存编辑状态，需要在退出前增加确认逻辑。

---

## 6. 刷新策略

商机详情中的操作可能影响客户详情中的多个区域。

### 6.1 操作影响范围

#### 编辑商机

需要刷新：

```text
商机详情
客户详情商机列表
```

#### 赢单 / 输单

需要刷新：

```text
商机详情
客户详情商机列表
客户摘要
合同列表
可能还有客户评分 / 热力值
```

#### 创建合同

需要刷新：

```text
商机详情关联合同
客户详情合同 tab
客户详情商机列表
```

### 6.2 第一阶段刷新策略

为了正确性优先，第一阶段可以在 `CustomerDetailSheet.vue` 中复用现有全量加载逻辑：

```ts
async function refreshAfterOpportunityChange(): Promise<void> {
  await loadAllData()
}
```

优点：

1. 实现简单；
2. 不容易漏刷新；
3. 风险低。

缺点：

1. 请求较多；
2. 性能不是最优。

### 6.3 第二阶段刷新优化

后续可以拆成细粒度加载函数：

```ts
async function refreshAfterOpportunityChange(): Promise<void> {
  await Promise.all([
    loadCustomerDetail(),
    loadOpportunities(),
    loadContracts(),
  ])
}
```

如果评分/热力值独立加载，还应加入对应刷新：

```ts
loadCustomerScore()
```

---

## 7. URL 深链与浏览器返回规划

### 7.1 第一阶段：不改 URL

第一阶段只做组件内部状态：

```text
点击商机
  → drilldownView = { type: 'opportunity', id }

点击返回商机列表
  → drilldownView = { type: 'none' }
```

优点：

1. 改动小；
2. 风险低；
3. 可以快速验证核心交互。

缺点：

1. 刷新页面不能恢复到具体商机详情；
2. 浏览器 Back 不知道内部下钻状态。

### 7.2 第二阶段：接入 query 状态

成熟版后续可增强为：

```text
/customers?customerId=19
/customers?customerId=19&tab=opportunities
/customers?customerId=19&tab=opportunities&opportunityId=88
```

对应关系：

| UI 状态 | URL |
|---|---|
| 客户列表 | `/customers` |
| 打开客户详情 | `/customers?customerId=19` |
| 打开客户详情商机 tab | `/customers?customerId=19&tab=opportunities` |
| 客户详情内下钻商机 | `/customers?customerId=19&tab=opportunities&opportunityId=88` |

浏览器 Back 目标：

```text
商机详情
  Back
商机列表
  Back
客户详情
  Back
客户列表
```

### 7.3 实现注意事项

1. 进入下钻使用 `router.push`，不要用 `replace`；
2. 返回商机列表时移除 `opportunityId`；
3. query 与组件状态必须定义一个 source of truth；
4. 第二阶段应单独实现，避免和第一阶段组件重构混在一起。

---

## 8. 测试计划

本次属于交互行为改造，应按 TDD 执行：先写失败测试，再改生产代码。

### 8.1 `OpportunitiesPanel` 测试

建议文件：

```text
CRM-Client/tests/components/OpportunitiesPanel.drilldown.spec.ts
```

#### 用例 1：点击商机行 emit 内部下钻事件

```text
given 客户详情商机列表有一条商机
when 用户点击商机行
then 组件 emit view-opportunity(opportunityId)
and 不调用 router.push
```

#### 用例 2：点击完整详情入口 emit open-full-page

```text
given 商机列表展示完整详情入口
when 用户点击完整详情入口
then 组件 emit open-full-page(opportunityId)
```

### 8.2 `CustomerDetailSheet` 测试

建议文件：

```text
CRM-Client/tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts
```

#### 用例 1：接收商机选择后展示内部详情

```text
given 客户详情 Sheet 已打开
and 当前 activePanel 是 opportunities
when OpportunitiesPanel emit view-opportunity(88)
then CustomerDetailSheet 渲染 OpportunityDetailContent
and OpportunityDetailContent 接收 opportunityId=88
and 页面中不存在第二个 Sheet
```

#### 用例 2：商机详情返回后回到商机列表

```text
given 已进入商机详情下钻
when OpportunityDetailContent emit back
then CustomerDetailSheet 重新展示 OpportunitiesPanel
and activePanel 仍是 opportunities
```

#### 用例 3：商机详情刷新通知父级刷新客户数据

```text
given 已进入商机详情下钻
when OpportunityDetailContent emit refresh
then CustomerDetailSheet 调用客户相关刷新逻辑
```

### 8.3 `OpportunityDetailSheet` 测试

建议文件：

```text
CRM-Client/tests/views/OpportunityDetailSheet.content-reuse.spec.ts
```

#### 用例 1：Sheet 壳渲染内容组件

```text
given OpportunityDetailSheet open=true
and opportunityId=88
then 渲染 OpportunityDetailContent
and 传入 opportunityId=88
```

#### 用例 2：内容组件 close 事件关闭 Sheet

```text
given OpportunityDetailSheet 已打开
when OpportunityDetailContent emit close
then OpportunityDetailSheet emit update:open false
```

### 8.4 回归验证

必须手动或自动验证：

1. `/opportunities` 页面点击商机仍打开详情 Sheet；
2. 客户详情 Sheet 原有 tabs 正常；
3. 客户详情商机 tab 正常加载；
4. 点击商机后不路由跳转；
5. 点击商机后不打开第二层 Sheet；
6. 点击“返回商机列表”能回到列表；
7. 客户详情关闭按钮仍关闭整个 Sheet；
8. Esc 行为没有焦点卡死；
9. 移动端没有横向溢出；
10. 商机动作成功后相关数据刷新。

### 8.5 设计系统合规测试补充

新增或调整测试时，除业务行为外还应覆盖以下设计系统约束：

1. 只存在一层 Sheet / Dialog 容器，客户详情内下钻不渲染第二个 Sheet；
2. 商机列表行可通过键盘触发内部下钻；
3. 行内“打开完整详情”按钮点击时不触发行点击；
4. 返回按钮是语义化 button，并有可读名称；
5. 图标按钮存在 `aria-label` 或等效可读名称；
6. loading / empty / error 状态至少有一种可检测的文案或重试/创建动作；
7. `embedded=true` 场景中，`OpportunityDetailContent` 不渲染独立 Sheet 外壳；
8. 切换 tab 时如果处于只读下钻状态，应退出下钻；如果未来存在未保存编辑状态，必须先触发确认。

---

## 9. UI / UX 细节规范

### 9.1 返回与关闭语义

内部下钻状态下必须同时区分：

```text
← 返回商机列表：只退出商机详情下钻
X 关闭：关闭整个客户详情 Sheet
```

不要让 `X` 同时承担返回和关闭两个含义。

### 9.2 Header 建议

客户详情内嵌商机详情：

```text
← 返回商机列表
商机名称
客户：客户名称
```

或者：

```text
客户名称 / 商机 / 商机名称
```

### 9.3 动效建议

内部下钻可以使用轻量横向过渡：

```text
商机列表 → 商机详情：内容向左进入
商机详情 → 商机列表：内容向右返回
```

要求：

1. 时长 150–250ms；
2. 只使用 transform / opacity；
3. 尊重 `prefers-reduced-motion`；
4. 不阻塞用户操作。

第一阶段可以先无动效，保证功能和结构正确。

### 9.4 可访问性

1. 返回按钮必须是语义化 button；
2. 图标按钮必须有 aria-label；
3. 下钻后焦点应移动到商机详情标题或返回按钮；
4. 返回列表后焦点应回到刚才点击的商机行；
5. 不出现多层 focus trap；
6. 键盘 Tab 顺序和视觉顺序一致。

### 9.5 移动端

1. 不出现双 Sheet；
2. 详情内容纵向滚动；
3. 底部操作区不遮挡内容；
4. 点击目标不小于 44px；
5. 返回按钮位置固定在用户预期区域。

### 9.6 令牌与视觉规范补充

根据 `foundations/color-tokens.md`、`foundations/spacing-layout.md`、`foundations/radius-elevation.md`，实现时不得新增任意色值、间距、圆角、阴影数值。

新增样式应优先使用以下 token：

```text
颜色：
$wolf-primary-v2
$wolf-primary-hover-v2
$wolf-primary-light-v2
$wolf-bg-page-v2
$wolf-bg-card-v2
$wolf-bg-hover-v2
$wolf-bg-muted-v2
$wolf-text-primary-v2
$wolf-text-secondary-v2
$wolf-text-tertiary-v2
$wolf-success-v2
$wolf-warning-v2
$wolf-danger-v2

间距：
$wolf-space-xs-v2
$wolf-space-sm-v2
$wolf-space-md-v2
$wolf-space-lg-v2
$wolf-space-xl-v2
$wolf-space-2xl-v2
$wolf-page-padding-v2
$wolf-card-padding-v2
$wolf-card-gap-v2
$wolf-section-gap-v2

移动端：
$wolf-page-padding-mobile-v2
$wolf-card-padding-mobile-v2
$wolf-section-gap-mobile-v2
$wolf-safe-area-top-v2
$wolf-safe-area-bottom-v2
$wolf-viewport-height-mobile-v2

圆角与阴影：
$wolf-radius-v2
$wolf-radius-sm-v2
$wolf-radius-lg-v2
$wolf-shadow-card-v2
$wolf-shadow-hover-v2
$wolf-shadow-modal-v2
$wolf-shadow-bottom-v2
```

若需要暗色模式适配，必须使用设计系统暗色 token，并单独验证对比度：

```text
$wolf-bg-page-dark-v2
$wolf-bg-card-dark-v2
$wolf-bg-hover-dark-v2
$wolf-text-primary-dark-v2
$wolf-text-secondary-dark-v2
$wolf-success-dark-v2
$wolf-warning-dark-v2
$wolf-danger-dark-v2
```

### 9.7 焦点与对比度补充

根据 `foundations/accessibility.md`：

1. 常规文字对比度不得低于 `$wolf-contrast-text-min-v2`，即 4.5:1；
2. 大文字对比度不得低于 `$wolf-contrast-large-text-min-v2`，即 3:1；
3. 图标与焦点指示对比度不得低于 `$wolf-contrast-icon-focus-min-v2`，即 3:1；
4. 返回按钮、完整详情入口、商机行、行内操作按钮都必须有可见焦点；
5. 焦点样式优先使用：

```text
$wolf-focus-ring-width-v2
$wolf-focus-ring-color-v2
$wolf-focus-ring-offset-v2
$wolf-focus-shadow-v2
```

不得使用 `outline: none` 后不提供替代焦点样式。

### 9.8 列表卡片交互补充

根据 `components/list-card.md`，客户详情 Sheet 内的商机列表应继续使用列表卡片而不是表格，除非数据量、排序筛选或跨行比较需求升级。

实施时必须注意：

1. 商机列表项最小高度为 44px；
2. 整行可点击时，行本身必须是键盘可达的交互元素；
3. 行内“打开完整详情”“更多操作”等按钮必须保留自身语义；
4. 不得让整行点击和行内按钮点击互相抢事件；
5. 行内按钮应阻止冒泡，避免点击“打开完整详情”同时触发内部下钻；
6. 加载、空状态、失败状态必须有明确说明和后续动作：
   - loading：显示骨架或加载提示；
   - empty：说明“暂无商机”，并在有权限时提供“新建商机”；
   - error：说明加载失败并提供重试。

### 9.9 详情内容信息层级补充

根据 `patterns/detail-page.md`，`OpportunityDetailContent.vue` 的信息层级应按以下顺序组织：

```text
顶部：对象标识 + 主要操作
中部：核心属性组 + 关联内容
底部：补充信息 + 历史/备注/低频信息
```

建议分组：

```text
对象标识：商机名称、阶段、客户上下文
核心属性：金额、预计成交日期、负责人、赢率、采购方式
关联内容：关联合同、联系人、跟进记录入口
补充信息：备注、创建时间、更新时间、低频字段
```

要求：

1. 每个属性组必须有明确标题；
2. 同组属性保持一致标签宽度和值对齐方式；
3. 低频属性进入可展开区域；
4. 展示区不直接混入复杂编辑表单；
5. 编辑动作通过按钮或独立表单触发。

### 9.10 按钮与危险操作补充

根据 `components/button.md`：

1. 内嵌商机详情每个任务区域只保留一个主按钮；
2. “打开完整商机详情”属于导航/跳转，不应设计为最高强调主按钮，优先用次级按钮、文本按钮或链接式按钮；
3. “赢单”“输单”“删除”等会改变业务状态的操作必须有明确文案和结果说明；
4. 危险或不可逆操作必须使用危险语义，并在执行前确认；
5. 提交或状态变更处理中要阻止重复提交，并展示处理中状态；
6. 图标按钮必须提供可读名称，例如 `aria-label="打开完整商机详情"`。

### 9.11 响应式与滚动边界补充

根据 `foundations/responsive-mobile.md` 和 `components/modal-sheet.md`：

1. 移动端优先满足 375px 小屏任务；
2. Sheet 内部内容可滚动，页面背景不得因 Sheet 内容产生横向滚动；
3. 信息密集区域优先转为卡片/属性组，避免固定像素宽容器；
4. 固定底部操作区必须预留 `$wolf-safe-area-bottom-v2`；
5. 移动端高度应使用 `$wolf-viewport-height-mobile-v2` 相关规则，避免 `100vh` 导致被浏览器 UI 或安全区域遮挡；
6. tabs 在窄视口可在标签栏内部滚动，但不能让整个页面横向滚动。

---

## 10. 代码规范约束

本项目 `CRM-Client/CLAUDE.md` 明确要求：

1. 禁用 `any`；
2. 禁用 `as any`；
3. 禁用 `@ts-ignore`；
4. 禁用非空断言 `!`；
5. 组件 Props/Emits 必须类型化；
6. Pinia Store 禁止 any 状态；
7. API 请求必须 Zod 校验；
8. 设计 token 必须使用 `variables-v2.scss` 与 `$wolf-xxx-v2`；
9. 禁止硬编码颜色、间距、圆角。

本次改造涉及 Vue 组件拆分，应特别注意：

1. 新组件 props/emits 全部声明类型；
2. 不为了快速迁移使用 `as any`；
3. 样式如果新增 SCSS，必须导入并使用 `variables-v2.scss`；
4. 不新造业务常量；
5. 权限码必须查已有定义，不能推断。

---

## 11. 实施阶段拆分

## Phase 0：准备与确认

### 任务

1. 确认 `OpportunityDetailSheet.vue` 当前所有业务动作；
2. 确认 `OpportunityDetailSheet.vue` 用到的 API、权限、store、router；
3. 确认 `CustomerDetailSheet.vue` 当前加载数据函数；
4. 确认 `OpportunitiesPanel.vue` 当前点击入口；
5. 确定第一阶段不做 URL query 深链；
6. 查阅并确认本次涉及的设计系统规范：
   - `components/modal-sheet.md`
   - `components/list-card.md`
   - `components/tabs.md`
   - `components/button.md`
   - `components/card.md`
   - `patterns/detail-page.md`
   - `foundations/accessibility.md`
   - `foundations/responsive-mobile.md`
   - `foundations/spacing-layout.md`
   - `foundations/color-tokens.md`
   - `foundations/motion-performance.md`
   - `foundations/radius-elevation.md`。

### 产出

1. 当前行为清单；
2. 需要保留的商机详情动作清单；
3. 第一阶段不做项清单。

---

## Phase 1：抽出 `OpportunityDetailContent.vue`

### 任务

1. 写 `OpportunityDetailSheet.content-reuse` 失败测试；
2. 新增 `OpportunityDetailContent.vue`；
3. 从 `OpportunityDetailSheet.vue` 移出详情内容和数据加载逻辑；
4. `OpportunityDetailSheet.vue` 改为渲染 `OpportunityDetailContent.vue`；
5. 保持原 `/opportunities` 页面行为不变。

### 验收

1. 原商机详情 Sheet 正常打开；
2. 原详情信息展示完整；
3. 原动作入口仍存在；
4. 新测试通过；
5. 无新增 lint/type 错误。

---

## Phase 2：改造 `OpportunitiesPanel.vue` 点击行为

### 任务

1. 写 `OpportunitiesPanel.drilldown` 失败测试；
2. 新增 typed emits；
3. 将默认点击从 `router.push` 改为 `emit('view-opportunity', id)`；
4. 如需完整详情入口，单独 emit `open-full-page`；
5. 调整列表行可点击状态和可访问性。

### 验收

1. 点击商机行 emit `view-opportunity`；
2. 默认点击不跳转路由；
3. 完整详情入口仍可触发外层跳转；
4. 键盘操作可触发主行为。

---

## Phase 3：`CustomerDetailSheet.vue` 接入内部下钻

### 任务

1. 写 `CustomerDetailSheet.opportunity-drilldown` 失败测试；
2. 增加 `DrilldownView` 状态；
3. 接入 `OpportunitiesPanel @view-opportunity`；
4. 在商机 tab 内条件渲染 `OpportunityDetailContent.vue`；
5. 实现 `backToOpportunityList`；
6. 实现 `openOpportunityFullPage`；
7. 实现 `refreshAfterOpportunityChange`。

### 验收

1. 客户详情商机 tab 点击商机后显示内部详情；
2. 不跳转；
3. 不打开第二层 Sheet；
4. 返回后仍在商机 tab；
5. 商机详情 emit refresh 后父级刷新客户相关数据。

---

## Phase 4：体验与稳定性增强

### 任务

1. 调整内嵌商机详情 header；
2. 增加“返回商机列表”；
3. 增加“打开完整商机详情”；
4. 检查关闭按钮语义；
5. 检查移动端表现；
6. 检查 focus 管理；
7. 检查 loading/error/empty 状态；
8. 确认无双遮罩、双 Sheet、focus trap 嵌套。

### 验收

1. 返回和关闭语义清晰；
2. 键盘可操作；
3. 移动端无明显布局问题；
4. 用户能从内嵌详情进入完整详情页。

---

## Phase 5：第二阶段 URL query 深链（建议后续单独做）

### 任务

1. 将客户详情 Sheet open 状态同步到 query；
2. 将 active tab 同步到 query；
3. 将下钻 opportunityId 同步到 query；
4. 实现浏览器 Back：商机详情 → 商机列表 → 客户详情 → 客户列表；
5. 刷新页面时恢复状态。

### 验收

1. URL 可表达客户详情内商机详情状态；
2. 浏览器 Back 行为符合用户预期；
3. 复制链接可恢复到对应客户和商机详情。

---

## 12. 推荐提交 / PR 拆分

### PR 1：商机详情内容组件抽取

包含：

1. 新增 `OpportunityDetailContent.vue`；
2. `OpportunityDetailSheet.vue` 复用内容组件；
3. 补充内容复用测试。

目标：

```text
不改变用户可见行为，只完成结构解耦。
```

### PR 2：客户详情商机内部下钻

包含：

1. `OpportunitiesPanel.vue` emit 点击事件；
2. `CustomerDetailSheet.vue` 增加下钻状态；
3. 客户详情内部渲染商机详情内容；
4. 返回商机列表；
5. 操作后刷新。

目标：

```text
完成核心体验改造。
```

### PR 3：体验增强与深链

包含：

1. query 状态；
2. 浏览器 Back；
3. 焦点恢复；
4. 列表滚动位置恢复；
5. 选中行高亮；
6. 动效优化。

目标：

```text
将交互补齐到成熟稳定状态。
```

---

## 13. 风险与规避

### 风险 1：直接嵌入 `OpportunityDetailSheet.vue` 导致 Sheet 套 Sheet

规避：

```text
禁止在 CustomerDetailSheet.vue 中直接渲染 OpportunityDetailSheet.vue。
必须渲染 OpportunityDetailContent.vue。
```

### 风险 2：拆分时破坏 `/opportunities` 页面原行为

规避：

1. 先写回归测试；
2. 保持 `OpportunityDetailSheet.vue` 对外接口尽量不变；
3. 第一阶段只做结构抽取，不改业务逻辑。

### 风险 3：商机详情动作依赖外层 Sheet 状态

规避：

1. 内容组件通过 emit 表达意图；
2. 外层分别处理 Sheet 场景和客户内嵌场景；
3. 不让内容组件直接假设自己处于某个路由或 Sheet 中。

### 风险 4：刷新范围不足导致客户详情数据陈旧

规避：

1. 第一阶段用 `loadAllData()` 保守刷新；
2. 后续再做细粒度刷新优化。

### 风险 5：权限码不一致

规避：

1. 不新造权限码；
2. 核对现有权限定义；
3. 将权限判断尽量复用原 `OpportunityDetailSheet.vue` 逻辑。

### 风险 6：组件拆分引入 TypeScript 问题

规避：

1. 明确 props/emits 类型；
2. 不使用 `any` / `as any`；
3. 必要时先抽类型定义；
4. 每个阶段跑 targeted type/lint/test。

### 风险 7：实现偏离目标设计系统

如果实现时沿用旧页面习惯，可能出现硬编码颜色、旧 `variables.scss`、Element Plus 风格残留、任意圆角/阴影、行点击与按钮点击冲突等问题。

规避：

1. Phase 0 中必须先查阅 `CRM-Docs/design-system/README.md` 及本计划列出的相关规范；
2. 新增样式只允许使用 `variables-v2.scss` 和 `$wolf-xxx-v2` token；
3. 商机列表继续遵循 `components/list-card.md`，不要为了快速实现改成表格或任意 div 列表；
4. Sheet 边界继续遵循 `components/modal-sheet.md`，不得引入第二层 Sheet；
5. PR 验收时增加“设计系统合规检查”小节，逐项确认 token、焦点、移动端、状态反馈。

---

## 14. 验收标准汇总

### 功能验收

- [ ] 客户详情 Sheet 商机 tab 中点击商机不跳转页面；
- [ ] 点击商机后不打开第二层 Sheet；
- [ ] 当前客户详情 Sheet 内展示商机详情；
- [ ] 商机详情显示“返回商机列表”；
- [ ] 返回后仍停留在客户详情商机 tab；
- [ ] 商机详情提供“打开完整商机详情”入口；
- [ ] `/opportunities` 页面原详情 Sheet 能力不受影响；
- [ ] 商机编辑/赢单/输单/创建合同后相关数据能刷新。

### 体验验收

- [ ] 返回和关闭语义清晰；
- [ ] 无双遮罩；
- [ ] 无双 Sheet；
- [ ] 无多层 focus trap；
- [ ] Esc / 关闭按钮行为符合预期；
- [ ] 移动端布局可用；
- [ ] 点击目标满足触控尺寸要求；
- [ ] loading/error/empty 状态完整。

### 代码验收

- [ ] 新增组件 props/emits 完整类型化；
- [ ] 无 `any`；
- [ ] 无 `as any`；
- [ ] 无 `@ts-ignore`；
- [ ] 无非空断言；
- [ ] 新增样式使用 `variables-v2.scss` token；
- [ ] 不硬编码颜色、间距、圆角；
- [ ] 有关键行为测试；
- [ ] targeted tests 通过；
- [ ] production component lint 通过。

### 设计系统验收

- [ ] 已查阅 `CRM-Docs/design-system/README.md` 并按优先级套用相关规范；
- [ ] Sheet 行为符合 `components/modal-sheet.md`，无第二层 Sheet、无双遮罩、无多层 focus trap；
- [ ] 商机列表符合 `components/list-card.md`，列表项高度、状态、键盘可达和行内操作不冲突；
- [ ] 客户详情 tabs 符合 `components/tabs.md`，只表达同一客户上下文下的并列内容；
- [ ] 商机详情内容符合 `patterns/detail-page.md`，顶部对象标识、中部属性组、底部补充信息层级清晰；
- [ ] 按钮符合 `components/button.md`，每个任务区域只有一个主操作，危险操作有确认；
- [ ] 新增视觉样式全部使用 `$wolf-xxx-v2` token；
- [ ] 亮色和暗色模式下文字、图标、焦点对比度满足 `foundations/accessibility.md`；
- [ ] 375px、768px、1024px、1440px 断点均无横向页面滚动；
- [ ] 移动端安全区域、底部操作区、内部滚动符合 `foundations/responsive-mobile.md`；
- [ ] 动效只使用 transform / opacity，时长符合 `$wolf-motion-state-duration-v2`，并尊重 reduced motion。

---

## 15. 建议执行顺序

最终建议按以下顺序实施：

```text
1. 写 OpportunityDetailSheet 内容复用测试
2. 抽 OpportunityDetailContent.vue
3. 保持 OpportunityDetailSheet 原行为通过测试
4. 写 OpportunitiesPanel 点击 emit 测试
5. 改 OpportunitiesPanel 默认点击行为
6. 写 CustomerDetailSheet 内部下钻测试
7. CustomerDetailSheet 接入 drilldownView
8. 接入 OpportunityDetailContent 内嵌展示
9. 打通返回商机列表
10. 打通 refreshAfterOpportunityChange
11. 验证 /opportunities 原商机详情 Sheet
12. 验证客户详情商机 tab 内部下钻
13. 补 UX / a11y / 移动端细节
14. 后续单独做 URL query 深链
```

---

## 16. 本次改造的边界建议

### 本次必须完成

1. `OpportunityDetailContent.vue` 抽取；
2. `OpportunityDetailSheet.vue` 薄壳化；
3. `OpportunitiesPanel.vue` emit 商机选择；
4. `CustomerDetailSheet.vue` 内部下钻；
5. 返回商机列表；
6. 保留完整商机详情入口；
7. 操作后刷新客户相关数据；
8. 关键行为测试。

### 本次不建议一起做

1. 全量重构 `OpportunityDetail.vue` 老页面；
2. 一次性接入完整 URL query 深链；
3. 同时改合同、回款、发票的下钻模式；
4. 大规模调整权限体系；
5. 大规模重构客户详情数据加载架构。

这些可以作为后续阶段处理。

---

## 17. 结论

该改造属于中等规模前端结构调整。主要工作量不在 API，而在组件职责拆分和交互状态管理。

最稳妥的路线是：

```text
先抽内容组件，保持原商机详情 Sheet 不变；
再改客户详情商机 tab 的点击行为；
最后在客户详情 Sheet 内部接入下钻视图。
```

这样可以避免 Sheet 套 Sheet，同时保留现有商机列表页体验，并为后续合同、回款、发票等关联对象下钻建立可复用模式。
