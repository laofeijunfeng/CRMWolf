# 审批中心页面改造设计文档

**日期**：2026-07-10
**类型**：前端页面改造
**优先级**：High

---

## 一、改造目标

将审批中心（ApprovalCenter.vue）从 Element Plus + 旧版 Design Tokens 迁移到 shadcn-vue + V2 Design Tokens，符合 CRMWolf 设计规范。

---

## 二、改造范围

### 2.1 改造文件

| 文件 | 行数 | 改造内容 |
|------|------|----------|
| `src/views/ApprovalCenter.vue` | 1024 | 主体页面改造 |
| `src/components/ApprovalProcessGeneric.vue` | 701 | 审批流程组件改造 |

### 2.2 改造策略

**方案 B：一次性完整重构**
- ApprovalCenter.vue + ApprovalProcessGeneric.vue 同步改造
- 桌面端 + 移动端同步改造
- 一个 PR，一次性提交

---

## 三、架构设计

### 3.1 页面结构（基于 MASTER.md §6.6 布局架构）

```
ApprovalCenter.vue
├── AppLayout（全局布局）
│   ├── SidebarV2（左侧导航，固定）
│   └── TopBarV2（顶部栏，56px，由 AppLayout 提供）
│
└── Content Area（内容区域）
    ├── ContextTabs（48px）
    │   ├── Tab 1: "待我审批" + Badge
    │   ├── Tab 2: "我已处理"
    │   └── Tab 3: "我提交的"
    │
    ├── FilterPanel（筛选区）
    │   └── Select: "单据类型"
    │
    ├── DataTable（桌面端表格）
    │   ├── 固定左列：单号（mono + 复制）
    │   ├── 固定右列：操作
    │   ├── 分页：底部固定
    │   └── 键盘快捷键：J/K、Enter、Esc
    │
    └── Mobile Card List（移动端卡片列表）
        ├── Card：单号 + 状态 + 实体 + 金额 + 提交人 + 时间 + 超时
        ├── 快速审批按钮（Touch Target ≥44pt）
        └── 移动端分页
│
└── ApprovalDetailSheet（详情 Sheet）
    ├── Sheet（宽度：桌面 480px，移动端 100%）
    │   ├── 基本信息 Card（Label + 文本）
    │   └── ApprovalProcessGeneric（审批流程 + 操作区）
    │
    └── QuickRejectDialog（移动端快速驳回弹窗）
```

---

## 四、数据流设计

### 4.1 状态管理（保持现有逻辑）

**Store**：`stores/approval.ts`（保持不变）

**State**：
- `loading`: boolean
- `pendingCount`: number
- `currentApprovalDetail`: ApprovalDetail | null

**Actions**：
- `fetchList(params)`: 获取审批列表
- `fetchDetail(entityType, entityId)`: 获取审批详情
- `approveEntity(...)`: 审批操作

### 4.2 ApprovalCenter.vue 数据流

```typescript
// State
const activeTab = ref<'pending' | 'processed' | 'submitted'>('pending')
const filterValues = reactive({ business_type: '' })
const pagination = reactive({ current: 1, pageSize: 20, total: 0 })
const tableData = ref<ApprovalListItem[]>([])
const sheetVisible = ref(false)
const selectedApproval = ref<ApprovalListItem | null>(null)

// Methods
const fetchList = async () => {
  const res = await approvalStore.fetchList({ ... })
  tableData.value = activeTab.value === 'pending'
    ? [...res.items].sort((a, b) => (b.overdue_hours ?? 0) - (a.overdue_hours ?? 0))
    : res.items
}

const handleTabChange = () => { ... }
const handleFilterChange = () => { ... }
const openDetailSheet = () => { ... }
const onSheetClosed = () => { ... }
```

---

## 五、组件选型与样式规范

### 5.1 ContextTabs

**来源**：`src/components/crmwolf/ContextTabs.vue`（封装 shadcn-vue Tabs）

**样式规范**：
- 高度：48px
- 背景：`$wolf-bg-card-v2`
- 圆角：`$wolf-radius-v2`（6px）
- 字号：`$wolf-font-size-body-v2`（14px）
- 字重 active：`$wolf-font-weight-semibold-v2`（600）

### 5.2 FilterPanel

**来源**：`src/components/crmwolf/FilterPanel.vue`

**样式规范**：
- 背景：`$wolf-bg-card-v2`
- 圆角：`$wolf-radius-v2`（6px）
- 内边距：`$wolf-card-padding-v2`（16px）
- 间距：`$wolf-space-md-v2`（16px）

### 5.3 DataTable

**来源**：`src/components/crmwolf/DataTable.vue`

**Columns 配置**：
- 单号（固定左列）：mono font + 点击复制
- 类型、实体、金额、提交人、时间、状态、超时
- 操作（固定右列）：详情、修改并重新提交

**样式规范**：
- 行高：44px
- 表头背景：`$wolf-bg-card-v2`
- 边框：`$wolf-border-light-v2`
- 字号：`$wolf-font-size-body-v2`（14px）

**键盘导航**：
- J/K：上下行
- Enter：打开详情 Sheet
- Esc：关闭 Sheet

### 5.4 ApprovalDetailSheet

**来源**：shadcn-vue Sheet

**样式规范**：
- 宽度：桌面 480px，移动端 100%
- 背景：`$wolf-bg-card-v2`
- 圆角：`$wolf-radius-v2`（6px）
- 内边距：`$wolf-card-padding-v2`（16px）
- 阴影：`$wolf-shadow-card-v2`

### 5.5 移动端卡片列表

**样式规范**（符合 UI/UX Pro Max）：
- Touch Target：`min-h-[44px]`
- 字号：`text-base`（16px）
- Safe Areas：`pb-[env(safe-area-inset-bottom)]`
- 圆角：`$wolf-radius-v2`（6px）
- 阴影：`$wolf-shadow-card-v2`

---

## 六、保留的业务逻辑

### 6.1 核心逻辑

- ✅ 超时排序：待我审批按 `overdue_hours` 降序
- ✅ 焦点回归：Sheet 关闭后焦点回到触发行
- ✅ 键盘快捷键：J/K、Enter、Esc
- ✅ 单号复制：使用 `navigator.clipboard.writeText`
- ✅ 快速审批：移动端卡片按钮（同意/驳回）
- ✅ 修改并重新提交：REJECTED 行显示按钮

### 6.2 ApprovalProcessGeneric 逻辑

- ✅ 提交审批、同意、驳回、撤回
- ✅ 乐观锁冲突处理（409）
- ✅ 发票文件上传（Task 6）
- ✅ 响应式布局（宽屏水平 timeline，窄屏垂直）

---

## 七、UI/UX Pro Max 检查清单

### 7.1 Accessibility (CRITICAL)

- ✅ `color-contrast`：文本对比度 4.5:1
- ⚠️ `focus-states`：DataTable 行聚焦态需要 `outline: 2px solid $wolf-primary-v2`
- ✅ `aria-labels`：shadcn-vue Button 内置 aria-label
- ✅ `keyboard-nav`：J/K、Enter、Esc、Tab
- ✅ `color-not-only`：状态 Badge 同时使用颜色 + 文字

### 7.2 Touch & Interaction (CRITICAL)

- ✅ `touch-target-size`：移动端按钮 `min-h-[44px]`
- ✅ `touch-spacing`：按钮间距 `$wolf-space-sm-v2`（8px）
- ✅ `loading-buttons`：`<Button :disabled="loading">` + Loader2
- ✅ `safe-area-awareness`：Sheet 操作区 `padding-bottom: env(safe-area-inset-bottom, 0)`
- ✅ `press-feedback`：shadcn-vue Button 内置 press feedback

### 7.3 Layout & Responsive (HIGH)

- ✅ `mobile-first`：先设计移动端卡片列表
- ✅ `breakpoint-consistency`：768px 断点
- ✅ `readable-font-size`：移动端正文 16px
- ✅ `horizontal-scroll`：DataTable 内部滚动
- ⚠️ `viewport-units`：Sheet 高度使用 `min(100vh, 100dvh)`

---

## 八、需要补充的设计

| 规则 | 补充设计 | 优先级 |
|------|----------|--------|
| `focus-states` | DataTable 行聚焦态 `outline: 2px solid $wolf-primary-v2` | HIGH |
| `viewport-units` | Sheet 高度使用 `min(100vh, 100dvh)` | HIGH |

---

## 九、实施步骤（概要）

1. **ApprovalCenter.vue 桌面端改造**
   - ContextTabs 替换 el-tabs
   - FilterPanel 替换筛选区
   - DataTable 替换 el-table
   - Sheet 替换 el-drawer
   - V2 design tokens

2. **ApprovalCenter.vue 移动端改造**
   - 移动端卡片列表（Card + Button）
   - 快速驳回弹窗（Dialog + Textarea）
   - Safe Areas + Touch Target

3. **ApprovalProcessGeneric.vue 改造**
   - V2 design tokens
   - shadcn-vue Button、Dialog、Skeleton、Empty
   - 保留所有审批逻辑

---

## 十、验收标准

### 10.1 功能验收

- ✅ 所有审批功能正常（提交、同意、驳回、撤回）
- ✅ 键盘快捷键正常（J/K、Enter、Esc）
- ✅ 单号复制正常
- ✅ 超时排序正常
- ✅ 移动端快速审批正常

### 10.2 样式验收

- ✅ 所有组件使用 V2 design tokens
- ✅ 无硬编码颜色、间距、圆角
- ✅ 符合 UI/UX Pro Max 检查清单
- ✅ 移动端 Touch Target ≥44pt

### 10.3 代码验收

- ✅ 无 TypeScript 错误
- ✅ 无 ESLint 错误
- ✅ 符合 CRM-Client 代码规范

---

## 十一、风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 审批逻辑遗漏 | HIGH | 保持现有 store 和 API 不变 |
| 移动端适配问题 | MEDIUM | 参考 Leads.vue 移动端实现 |
| 键盘快捷键冲突 | LOW | 保留现有键盘监听逻辑 |

---

## 十二、参考文档

- [CRM-Docs/design-system/MASTER.md](../../CRM-Docs/design-system/MASTER.md)
- [CRM-Docs/design-system/pages/approval-center.md](../../CRM-Docs/design-system/pages/approval-center.md)
- [CRM-Client/CLAUDE.md](../../CRM-Client/CLAUDE.md)
- [UI/UX Pro Max Quick Reference](~/.claude/skills/ui-ux-pro-max/README.md)

---

**版本**：V1.0
**最后更新**：2026-07-10