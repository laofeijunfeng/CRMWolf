# 列表页统一优化实施计划

**项目**：CRMWolf 前端模块
**文档类型**：实施计划
**版本**：V1.0
**日期**：2026-07-09

---

## 一、项目背景

### 1.1 目标

将 5 个列表页（客户管理、商机管理、合同管理、回款管理、发票管理）统一优化，遵循：
- **V2 Design System**（MASTER.md）
- **shadcn-vue 优先原则**（§3）
- **移动端优先设计**（§1.3）

### 1.2 参考页面

**Leads.vue** 已完成优化，作为标准模板：
- ✅ TopBar 操作按钮集成（`useHeaderStore`）
- ✅ SearchCard + DataTable 布局
- ✅ V2 Design Tokens
- ✅ Flexbox 高度管理（`min-height: 0; flex: 1;`）

---

## 二、关键决策总结

### 2.1 用户确认的方案

| 决策项 | 用户选择 | 影响 |
|--------|---------|------|
| **快捷筛选标签栏** | C. 改用 ContextTabs | 需开发新组件 |
| **活跃筛选汇总区** | B. 移除 | 简化 UI |
| **Payments.vue 布局** | 拆分成 2 个独立页面 | Sidebar 菜单调整 |
| **搜索筛选区** | C. 开发新组件 FilterPanel | 替代 SearchCard |

---

## 三、实施阶段规划

### Phase 0：组件开发（预计 3-4 天）

#### 3.1 ContextTabs 组件开发

**设计规范**：MASTER.md §6.3

| 属性 | 值 | Token |
|------|-----|-------|
| **高度** | `48px` | - |
| **背景** | `#FFFFFF` | `$wolf-bg-card-v2` |
| **Tab 高度** | `40px` | - |
| **Tab 圆角** | `6px` | `$wolf-radius-v2` |
| **字号** | `14px` | `$wolf-font-size-body-v2` |
| **字重 default** | `500` | `$wolf-font-weight-medium-v2` |
| **字重 active** | `600` | `$wolf-font-weight-semibold-v2` |

**组件位置**：`src/components/crmwolf/ContextTabs.vue`

**功能要求**：
- ✅ 支持多个 Tab 切换
- ✅ Active 状态：白色背景 + 阴影
- ✅ Hover 状态：背景变化
- ✅ 底部指示条（可选）
- ✅ Props：`tabs: TabItem[]`, `activeTab: string`
- ✅ Events：`@change`

**状态定义**（Segmented Control 模式 - MASTER.md §5.6）：

| 状态 | 背景 | 文字 | 阴影 |
|------|------|------|------|
| **Default** | 透明 | `#64748B` | 无 |
| **Hover** | 透明 | `#2563EB` | 无 |
| **Active** | `#FFFFFF` | `#2563EB` | `0 1px 2px rgba(0,0,0,0.05)` |

**容器样式**：
```scss
.context-tabs-container {
  display: flex;
  padding: 4px;
  background: $wolf-bg-muted-v2;  // #F1F5FD
  border-radius: $wolf-radius-lg-v2;  // 8px
  gap: $wolf-space-xs-v2;  // 4px
}
```

**Item 样式**：
```scss
.context-tab-item {
  height: 40px;
  padding: 0 $wolf-space-lg-v2;  // 16px
  font-size: $wolf-font-size-body-v2;  // 14px
  font-weight: $wolf-font-weight-medium-v2;  // 500
  border-radius: $wolf-radius-v2;  // 6px
  cursor: pointer;
  transition: all $wolf-transition-v2;  // 150ms ease

  &.active {
    background: $wolf-bg-card-v2;
    color: $wolf-primary-v2;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
  }

  &:hover:not(.active) {
    color: $wolf-primary-v2;
  }
}
```

---

#### 3.2 FilterPanel 组件开发

**替代**：SearchCard

**设计规范**：MASTER.md §5.2 Input

**组件位置**：`src/components/crmwolf/FilterPanel.vue`

**功能要求**：
- ✅ 关键词搜索（Input + Icon）
- ✅ 多个筛选字段（Select/Dropdown）
- ✅ 重置按钮
- ✅ 展开/收起（可选）
- ✅ Props：`fields: FilterField[]`, `values: Record<string, any>`
- ✅ Events：`@search`, `@reset`, `@change`

**FilterField 类型定义**：
```typescript
interface FilterField {
  key: string
  label: string
  type: 'text' | 'select' | 'date' | 'date-range'
  placeholder?: string
  options?: { value: string | number, label: string }[]
}
```

**布局规范**：
```scss
.filter-panel {
  display: flex;
  align-items: center;
  gap: $wolf-space-md-v2;  // 12px
  padding: $wolf-space-lg-v2;  // 16px
  background: $wolf-bg-card-v2;
  border-radius: $wolf-radius-v2;
  box-shadow: $wolf-shadow-card-v2;

  .filter-search {
    flex: 1;
    min-width: 200px;
  }

  .filter-fields {
    display: flex;
    gap: $wolf-space-sm-v2;  // 8px
  }

  .filter-actions {
    display: flex;
    gap: $wolf-space-xs-v2;  // 4px
  }
}
```

**移动端适配**（MASTER.md §10.2）：
```scss
@media (max-width: $wolf-breakpoint-md-v2 - 1) {
  .filter-panel {
    flex-direction: column;
    align-items: stretch;

    .filter-fields {
      flex-wrap: wrap;
    }
  }
}
```

---

#### 3.3 DataTable 组件更新

**检查项**：
- ✅ 是否已支持自定义单元格模板（`#cell-{key}`）
- ✅ 是否已支持分页（`page`, `pageSize`, `total`）
- ✅ 是否已支持加载状态（`loading`）
- ✅ 是否已支持空状态（`emptyTitle`）

**如果缺少功能**：需要扩展 DataTable 组件

---

### Phase 1：Payments.vue 拆分（预计 1 天）

#### 3.4 新建 PaymentPlans.vue

**路由**：`/payments/plans`

**布局**：TopBar + ContextTabs + FilterPanel + DataTable

**ContextTabs**：
- 全部计划
- 待确认
- 已确认
- 已完成
- 已逾期

**操作按钮**（TopBar）：
- 新建回款计划

**表格列**：
- 计划编号
- 客户名称
- 合同名称
- 计划金额
- 计划日期
- 状态
- 操作（查看、编辑、删除）

---

#### 3.5 新建 PaymentRecords.vue

**路由**：`/payments/records`

**布局**：TopBar + ContextTabs + FilterPanel + DataTable

**ContextTabs**：
- 全部记录
- 待确认
- 已确认

**操作按钮**（TopBar）：
- 登记回款

**表格列**：
- 记录编号
- 客户名称
- 合同名称
- 回款金额
- 回款日期
- 状态
- 操作（查看、编辑、删除）

---

#### 3.6 Sidebar 菜单调整

**修改文件**：`src/components/layout/SidebarV2.vue`（或对应文件）

**原菜单**：
```
财务流程
├── 合同管理
├── 回款管理  ← 单一入口
└── 发票管理
```

**新菜单**：
```
财务流程
├── 合同管理
├── 回款计划  ← 新增
├── 回款记录  ← 新增
└── 发票管理
```

**路由配置**：`src/router/index.ts`

```typescript
// 原路由
{
  path: '/payments',
  name: 'Payments',
  component: () => import('@/views/Payments.vue'),
}

// 新路由
{
  path: '/payments/plans',
  name: 'PaymentPlans',
  component: () => import('@/views/PaymentPlans.vue'),
  meta: { title: '回款计划' },
},
{
  path: '/payments/records',
  name: 'PaymentRecords',
  component: () => import('@/views/PaymentRecords.vue'),
  meta: { title: '回款记录' },
},
```

---

### Phase 2：简单页面优化（预计 2-3 天）

#### 3.7 Opportunities.vue 优化

**改动清单**：

1. **布局改造**
   - ❌ 移除 `min-height: calc(100vh - 48px)`
   - ✅ 改用 `min-height: 0; flex: 1;`
   - ✅ 导入 `variables-v2.scss`

2. **TopBar 集成**
   ```typescript
   watchEffect(() => {
     headerStore.setActions([
       {
         id: 'create',
         label: '新建商机',
         icon: Plus,
         type: 'primary',
         handler: () => router.push('/opportunities/create'),
         visible: canCreateOpportunity.value,
       },
     ])
   })

   onUnmounted(() => {
     headerStore.clear()
   })
   ```

3. **组件替换**
   - ❌ `el-button` → `Button`（shadcn-vue）
   - ❌ `el-table` → `DataTable`（crmwolf）
   - ❌ `el-pagination` → DataTable 内置分页
   - ❌ `ElMessageBox` → `confirmDialog`
   - ❌ `ElMessage` → `toast`

4. **快捷筛选标签栏** → ContextTabs
   ```vue
   <ContextTabs
     :tabs="[
       { key: 'all', label: '所有商机' },
       { key: 'active', label: '跟进中' },
       { key: 'won', label: '已赢单' },
       { key: 'lost', label: '已输单' },
     ]"
     :active-tab="activeTab"
     @change="handleTabChange"
   />
   ```

5. **搜索筛选区** → FilterPanel
   ```vue
   <FilterPanel
     :fields="[
       { key: 'keyword', type: 'text', placeholder: '搜索商机名称' },
       { key: 'status', type: 'select', placeholder: '状态', options: statusOptions },
     ]"
     :values="filterValues"
     @search="handleSearch"
     @reset="handleReset"
   />
   ```

---

#### 3.8 Invoices.vue 优化

**改动清单**（同 Opportunities.vue）：

1. **布局改造**（同上）

2. **TopBar 集成**
   - 新建发票按钮

3. **组件替换**（同上）

4. **快捷筛选标签栏** → ContextTabs
   - 全部申请
   - 待审批
   - 已批准
   - 已开票

5. **搜索筛选区** → FilterPanel
   - 搜索申请单号/客户名称
   - 客户筛选
   - 发票类型筛选

---

### Phase 3：复杂页面优化（预计 3-4 天）

#### 3.9 Customers.vue 优化

**改动清单**：

1. **布局改造**（同上）

2. **TopBar 集成**
   - AI 创建客户
   - 手动创建

3. **组件替换**（同上）

4. **快捷筛选标签栏** → ContextTabs
   - 所有客户
   - 我的客户
   - 公海客户

5. **搜索筛选区** → FilterPanel
   - 客户名称搜索
   - 城市筛选
   - 状态筛选
   - 热力值筛选

6. **移除活跃筛选汇总区**
   - ❌ 删除 `active-filter-summary` 相关代码

7. **保留业务逻辑**
   - ✅ 退回公海弹窗 → `AlertDialog`（shadcn-vue）
   - ✅ 输单弹窗 → `AlertDialog`
   - ✅ 赢单确认 → `confirmDialog`

---

#### 3.10 Contracts.vue 优化

**改动清单**：

1. **布局改造**（同上）

2. **TopBar 集成**
   - 新建合同

3. **组件替换**（同上）

4. **快捷筛选标签栏** → ContextTabs（**7 个标签**）
   - 全部合同
   - 草稿
   - 审批中
   - 已签署
   - 生效中
   - 已到期
   - 已终止

**⚠️ 特殊处理**：7 个标签可能过多，考虑以下方案：

**方案 A**：分成两组
- **ContextTabs**：全部、草稿、审批中、已签署、已生效
- **FilterPanel**：状态下拉筛选（包含全部状态）

**方案 B**：更多按钮
- **ContextTabs**：全部、草稿、审批中、已签署、已生效 + "更多"下拉

**推荐**：方案 A（用户可快速切换常用状态，通过 FilterPanel 查看所有状态）

---

### Phase 4：测试与验证（预计 1 天）

#### 3.11 功能测试

**测试清单**：

| 页面 | 测试项 | 状态 |
|------|-------|------|
| **所有页面** | 布局无滚动问题 | ⬜ |
| **所有页面** | TopBar 操作按钮显示正确 | ⬜ |
| **所有页面** | ContextTabs 切换正常 | ⬜ |
| **所有页面** | FilterPanel 筛选正常 | ⬜ |
| **所有页面** | DataTable 分页正常 | ⬜ |
| **Customers** | 退回公海弹窗正常 | ⬜ |
| **Customers** | 输单/赢单功能正常 | ⬜ |
| **Payments** | 菜单导航正确 | ⬜ |
| **Payments** | 两个页面切换正常 | ⬜ |

---

#### 3.12 设计规范验证

**强制验证项**（MASTER.md §2）：

| 检查项 | Token | 状态 |
|--------|-------|------|
| **导入 V2 Token** | `@use '@/styles/variables-v2.scss' as *;` | ⬜ |
| **使用 -v2 后缀** | `$wolf-*-v2` | ⬜ |
| **无硬编码颜色** | - | ⬜ |
| **无硬编码间距** | - | ⬜ |
| **无硬编码圆角** | - | ⬜ |
| **无固定高度计算** | `min-height: calc(100vh - XXpx)` | ⬜ |

---

## 四、技术规范总结

### 4.1 强制使用

```scss
// ✅ 正确
@use '@/styles/variables-v2.scss' as *;

.xxx-page {
  padding: $wolf-page-padding-v2;  // 24px
  background: $wolf-bg-page-v2;    // #F7F7F5
  display: flex;
  flex-direction: column;
  gap: $wolf-section-gap-v2;      // 24px
  min-height: 0;
  flex: 1;
}

// ❌ 错误
@use '@/styles/variables.scss' as *;
min-height: calc(100vh - 48px);
```

---

### 4.2 TopBar 集成模式

```typescript
import { useHeaderStore } from '@/stores/header'
import { watchEffect, onUnmounted } from 'vue'
import { Plus } from 'lucide-vue-next'

const headerStore = useHeaderStore()

watchEffect(() => {
  headerStore.setActions([
    {
      id: 'create',
      label: '新建',
      icon: Plus,
      type: 'primary',
      handler: () => router.push('/xxx/create'),
      visible: canCreate.value,
      ariaLabel: '新建XXX',
    },
  ])
})

onUnmounted(() => {
  headerStore.clear()
})
```

---

### 4.3 API 错误处理（MASTER.md §3.7）

```typescript
// ✅ 正确
import { handleApiError } from '@/utils/errorHandler'
import { toast } from 'vue-sonner'
import { confirmDialog } from '@/utils/confirmDialog'

try {
  await api.deleteCustomer(id)
  toast.success('客户删除成功')
} catch (error) {
  handleApiError(error, '删除客户')
}

// ❌ 错误
import { ElMessage, ElMessageBox } from 'element-plus'
ElMessage.success('删除成功')
```

---

### 4.4 shadcn-vue 优先原则（MASTER.md §3）

**使用流程**：
```
需要 UI 组件
    ↓
/shadcn-vue 查找组件和使用规范
    ↓
获取正确的组件名称、API、示例
    ↓
在代码中使用
```

**示例**：
```bash
/shadcn-vue 查找分页组件
/shadcn-vue AlertDialog 如何使用
/shadcn-vue 添加 Dialog 组件
```

---

## 五、风险评估

### 5.1 技术风险

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| **ContextTabs 组件开发复杂** | 延期 1-2 天 | 参考 shadcn-vue Tabs 组件 |
| **FilterPanel 组件功能不足** | 筛选功能缺失 | 逐步扩展字段类型 |
| **Payments 拆分影响现有数据** | 路由失效 | 保留旧路由重定向 |

---

### 5.2 业务风险

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| **用户习惯改变** | 投诉/困惑 | 提供迁移指南 |
| **功能遗漏** | 业务中断 | 完整测试清单 |

---

## 六、验收标准

### 6.1 功能验收

- ✅ 所有列表页无滚动问题
- ✅ TopBar 操作按钮显示正确
- ✅ ContextTabs 切换正常
- ✅ FilterPanel 筛选正常
- ✅ DataTable 分页正常
- ✅ 所有业务功能正常（退回公海、输单、赢单等）

---

### 6.2 设计规范验收

- ✅ 所有页面使用 V2 Design Tokens
- ✅ 无硬编码颜色/间距/圆角
- ✅ 无固定高度计算（`calc(100vh - XXpx)`）
- ✅ 移动端适配正常
- ✅ Touch Target ≥ 44px（移动端）

---

## 七、时间估算

| 阶段 | 预计时间 | 依赖 |
|------|---------|------|
| **Phase 0：组件开发** | 3-4 天 | 无 |
| **Phase 1：Payments 拆分** | 1 天 | Phase 0 |
| **Phase 2：简单页面优化** | 2-3 天 | Phase 0 |
| **Phase 3：复杂页面优化** | 3-4 天 | Phase 0 |
| **Phase 4：测试与验证** | 1 天 | All |
| **总计** | **10-13 天** | - |

---

## 八、附录

### 8.1 文件清单

**新建文件**：
- `src/components/crmwolf/ContextTabs.vue`
- `src/components/crmwolf/FilterPanel.vue`
- `src/views/PaymentPlans.vue`
- `src/views/PaymentRecords.vue`

**修改文件**：
- `src/views/Customers.vue`
- `src/views/Opportunities.vue`
- `src/views/Contracts.vue`
- `src/views/Invoices.vue`
- `src/router/index.ts`
- `src/components/layout/SidebarV2.vue`（菜单配置）
- `src/components/crmwolf/index.ts`（导出新组件）

---

### 8.2 参考文档

- **MASTER.md**：`CRM-Docs/design-system/MASTER.md`
- **list-page.md**：`CRM-Docs/design-system/pages/list-page.md`
- **README.md**：`CRM-Docs/design-system/README.md`
- **Leads.vue**：`CRM-Client/src/views/Leads.vue`（标准模板）

---

---

## 九、移动端适配规范（MASTER.md §1.3 + §10）

> ⚠️ **CRITICAL**：违反移动端规范将导致用户体验严重下降

### 9.1 Mobile-First 原则

| 原则 | Token | 值 | UI/UX Pro Max 规则 |
|------|-------|-----|-------------------|
| **Mobile-First** | - | 先设计移动端，再扩展桌面端 | §5: `mobile-first` |
| **Touch Target ≥44px** | `$wolf-touch-target-min-v2` | `44px` | §2: `touch-target-size` |
| **16px Body Text** | `$wolf-font-size-body-mobile-v2` | `16px` | §5: 避免 iOS auto-zoom |
| **Safe Areas** | `$wolf-safe-area-*-v2` | `env(safe-area-inset-*)` | §2: `safe-area-awareness` |
| **Dynamic Viewport** | `$wolf-viewport-height-mobile-v2` | `min(100vh, 100dvh)` | §5: `viewport-units` |

### 9.2 断点系统（MASTER.md §10.1）

| 断点 | Token | 值 | 设备 | 导航模式 |
|------|-------|-----|------|---------|
| **xs** | `$wolf-breakpoint-xs-v2` | `375px` | 小手机（iPhone SE） | Bottom Nav |
| **sm** | `$wolf-breakpoint-sm-v2` | `768px` | 平板竖屏（iPad Mini） | Sidebar 可折叠 |
| **md** | `$wolf-breakpoint-md-v2` | `1024px` | 平板横屏 / 小桌面 | Sidebar 显示 |
| **lg** | `$wolf-breakpoint-lg-v2` | `1440px` | 大桌面 | Sidebar 固定 |

### 9.3 间距适配

| 断点 | Token | 页面边距 | 卡片间距 | 卡片内边距 |
|------|-------|---------|---------|-----------|
| **xs（移动端）** | `$wolf-page-padding-mobile-v2` | `16px` | `12px` | `12px` |
| **md+（桌面端）** | `$wolf-page-padding-v2` | `24px` | `24px` | `16px` |

### 9.4 移动端字体尺寸（iOS Auto-Zoom 防护）

| 场景 | Token | 值 | 说明 |
|------|-------|-----|------|
| **移动端正文** | `$wolf-font-size-body-mobile-v2` | `16px` | 避免 iOS Safari auto-zoom |
| **移动端标题** | `$wolf-font-size-title-mobile-v2` | `18px` | 更醒目 |
| **移动端辅助** | `$wolf-font-size-caption-mobile-v2` | `14px` | 辅助信息 |

**关键规则**：
- ✅ 移动端 input/textarea 必须使用 `16px` 字号
- ❌ 禁止移动端使用 `< 16px` 字号（iOS Safari 会自动放大页面）

### 9.5 安全区域（Safe Areas）

```scss
// TopBar
.top-bar {
  padding-top: $wolf-safe-area-top-v2;
}

// Bottom Nav
.bottom-nav {
  padding-bottom: $wolf-safe-area-bottom-v2;
}
```

### 9.6 响应式导航切换

| 断点 | 导航模式 | Sidebar | TopBar | Bottom Nav |
|------|---------|---------|--------|-----------|
| **≥1024px（桌面）** | Sidebar + TopBar | 220px 固定 | 56px | 隐藏 |
| **<1024px（移动）** | TopBar + Bottom Nav | 隐藏 | 56px | 56px，最多 5 项目 |

### 9.7 ContextTabs 移动端适配

```scss
.context-tabs-container {
  // 桌面端
  @media (min-width: $wolf-breakpoint-md-v2) {
    padding: 4px;
    gap: $wolf-space-xs-v2;
  }

  // 移动端：更紧凑
  @media (max-width: $wolf-breakpoint-md-v2 - 1) {
    padding: 2px;
    gap: 2px;
    overflow-x: auto;  // 允许横向滚动
    -webkit-overflow-scrolling: touch;
  }
}

.context-tab-item {
  // 移动端：Touch Target 合规
  @media (max-width: $wolf-breakpoint-md-v2 - 1) {
    min-height: 44px;  // Touch Target 合规
    padding: 0 $wolf-space-md-v2;
  }
}
```

### 9.8 FilterPanel 移动端适配

```scss
.filter-panel {
  display: flex;
  flex-wrap: wrap;  // 响应式换行
  gap: $wolf-space-sm-v2;

  @media (max-width: $wolf-breakpoint-md-v2 - 1) {
    flex-direction: column;
    align-items: stretch;
    gap: $wolf-space-xs-v2;
  }
}

.filter-search,
.filter-fields input,
.filter-fields select {
  // 移动端：Touch Target 合规
  @media (max-width: $wolf-breakpoint-md-v2 - 1) {
    min-height: 44px;
    font-size: $wolf-font-size-body-mobile-v2;  // 16px，避免 iOS auto-zoom
  }
}
```

### 9.9 DataTable 移动端适配

```scss
.data-table-wrapper {
  // 移动端：允许横向滚动
  @media (max-width: $wolf-breakpoint-md-v2 - 1) {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }
}

// 移动端表格策略：
// 1. 简化列数（仅显示核心信息）
// 2. 允许表格横向滚动（页面主体禁止）
// 3. 固定首列（如客户名称）
```

### 9.10 移动端禁止事项（UI/UX Pro Max）

| 禁止项 | 原因 | Token |
|--------|------|-------|
| ❌ 固定 px 容器宽度 | 导致横向滚动 | - |
| ❌ `user-scalable=no` | 违反 Accessibility | - |
| ❌ `100vh` | iOS Safari 地址栏问题 | 使用 `min(100vh, 100dvh)` |
| ❌ Touch targets 在 notch 下方 | 无法点击 | `$wolf-safe-area-top-v2` |
| ❌ Bottom Nav 超过 5 项目 | 损害可发现性 | `$wolf-bottom-nav-max-items-v2: 5` |
| ❌ Icon-only Bottom Nav | 损害可发现性 | 必须有 Icon + Text Label |
| ❌ 移动端 input 字号 < 16px | iOS auto-zoom | `$wolf-font-size-body-mobile-v2` |
| ❌ 页面主体横向滚动 | 用户体验差 | `$wolf-overflow-x-mobile-v2: hidden` |

---

## 十、无障碍规范（MASTER.md §8）

> ⚠️ **CRITICAL**：违反无障碍规范将导致 WCAG 不合规

### 10.1 Focus 状态规范

| Token | 值 | 说明 |
|-------|-----|------|
| `$wolf-focus-ring-width-v2` | `2px` | Focus ring 宽度（WCAG 2.4.7 合规） |
| `$wolf-focus-ring-color-v2` | `rgba(#2563EB, 0.5)` | Focus ring 颜色 |
| `$wolf-focus-ring-offset-v2` | `2px` | Focus ring 偏移 |

**实现示例**：

```scss
// ✅ 正确：可见 focus ring
.button:focus-visible {
  outline: $wolf-focus-ring-width-v2 solid $wolf-focus-ring-color-v2;
  outline-offset: $wolf-focus-ring-offset-v2;
}

// ❌ 错误：移除 focus ring（违反 WCAG）
.button:focus {
  outline: none;
}
```

### 10.2 Reduced Motion 支持（MASTER.md §8.3）

| Token | 值 | 说明 |
|-------|-----|------|
| `$wolf-reduced-motion-duration-v2` | `0.01ms` | `prefers-reduced-motion` 时的动画时长 |

**实现示例**：

```scss
.context-tab-item {
  transition: all 150ms ease;

  @media (prefers-reduced-motion: reduce) {
    transition-duration: $wolf-reduced-motion-duration-v2;
  }
}
```

### 10.3 Screen Reader 支持

| 规则 | 实现方式 | MASTER.md 章节 |
|------|---------|---------------|
| **aria-label** | 图标按钮必须有 aria-label | §8.4 |
| **aria-live** | 动态内容使用 aria-live | §8.4 |
| **语义化标签** | 使用 button、label、nav | §8.4 |
| **Tab 顺序** | 匹配视觉顺序 | §8.4 |
| **Focus 管理** | 错误后 auto-focus 第一个错误字段 | §8.4 |

**ContextTabs 无障碍示例**：

```vue
<nav class="context-tabs" role="tablist" aria-label="筛选条件">
  <button
    v-for="tab in tabs"
    :key="tab.key"
    role="tab"
    :aria-selected="activeTab === tab.key"
    :aria-controls="`tabpanel-${tab.key}`"
  >
    {{ tab.label }}
  </button>
</nav>
```

### 10.4 对比度验证

| 类型 | Token | 对比度 | WCAG 等级 |
|------|-------|--------|----------|
| **主文字** | `$wolf-text-primary-v2: #0F172A` | 15:1 | AAA ✅ |
| **次文字** | `$wolf-text-secondary-v2: #64748B` | 4.5:1 | AA ✅ |
| **辅助文字** | `$wolf-text-tertiary-v2: #94A3B8` | 3:1 | AA Large ✅ |

**暗色模式对比度（独立验证）**：

| 类型 | Token | 对比度 | WCAG 等级 |
|------|-------|--------|----------|
| **暗色主文字** | `$wolf-text-primary-dark-v2: #F8FAFC` on `#0F172A` | 15:1 | AAA ✅ |
| **暗色次文字** | `$wolf-text-secondary-dark-v2: #CBD5E1` on `#1E293B` | 4.5:1 | AA ✅ |

---

## 十一、暗色模式支持策略（MASTER.md §4.1）

> **UI/UX Pro Max 规则**：Dark mode uses desaturated / lighter tonal variants, not inverted colors

### 11.1 暗色模式 Token（已定义）

| 角色 | Token | Hex | 说明 |
|------|-------|-----|------|
| **页面背景** | `$wolf-bg-page-dark-v2` | `#0F172A` | Slate-900 |
| **卡片背景** | `$wolf-bg-card-dark-v2` | `#1E293B` | Slate-800 |
| **Sidebar 背景** | `$wolf-bg-sidebar-dark-v2` | `#1E293B` | Slate-800 |
| **Hover 背景** | `$wolf-bg-hover-dark-v2` | `#334155` | Slate-700 |
| **主文字** | `$wolf-text-primary-dark-v2` | `#F8FAFC` | 15:1 contrast |
| **次文字** | `$wolf-text-secondary-dark-v2` | `#CBD5E1` | 4.5:1 contrast |

### 11.2 实施策略

**Phase 0（组件开发）**：
- ✅ ContextTabs、FilterPanel 组件必须支持暗色模式
- ✅ 使用 CSS 变量切换主题（非硬编码）

**Phase 1-3（页面优化）**：
- ⏳ 暂不实施暗色模式（降低初期复杂度）
- ⏳ 预留 CSS 变量架构

**Phase 4（测试与验证）**：
- ⏳ 验证暗色模式对比度独立符合 WCAG AA

### 11.3 CSS 变量架构（预留）

```scss
// 亮色模式（默认）
:root {
  --wolf-bg-page: #{$wolf-bg-page-v2};
  --wolf-bg-card: #{$wolf-bg-card-v2};
  --wolf-text-primary: #{$wolf-text-primary-v2};
  // ...
}

// 暗色模式
[data-theme="dark"] {
  --wolf-bg-page: #{$wolf-bg-page-dark-v2};
  --wolf-bg-card: #{$wolf-bg-card-dark-v2};
  --wolf-text-primary: #{$wolf-text-primary-dark-v2};
  // ...
}
```

---

## 十二、性能规范（MASTER.md §9）

### 12.1 动画性能

| 规则 | 要求 | Token |
|------|------|-------|
| **仅使用 transform/opacity** | 避免 animating width/height/top/left | - |
| **避免 layout reflow** | 批量 DOM 读写 | - |
| **requestAnimationFrame** | 复杂动画 | - |

### 12.2 响应时间（MASTER.md §9.2）

| 操作 | 最大延迟 | 说明 |
|------|---------|------|
| **Tap 反馈** | `100ms` | 用户感知即时 |
| **Hover 反馈** | `150ms` | `$wolf-transition-v2` |
| **Loading 显示** | `300ms` | 避免 spinner 闪烁 |

### 12.3 ContextTabs 动画规范

| 属性 | 值 | Token |
|------|-----|-------|
| **内容切换** | `150ms fade` | `$wolf-transition-v2` |
| **背景变化** | `150ms ease-out` | - |
| **文字颜色** | `150ms ease-out` | - |
| **Reduced motion** | `0.01ms` | `$wolf-reduced-motion-duration-v2` |

### 12.4 虚拟化列表（MASTER.md §9.1）

| 阈值 | 说明 |
|------|------|
| **>50 条数据** | 启用虚拟化（`vue-virtual-scroller`） |

### 12.5 分页加载

| 默认 | 可选 |
|------|------|
| **20 条/页** | 10 / 20 / 50 / 100 |

---

## 十三、shadcn-vue Skill 强制使用说明（MASTER.md §3.0）

> ⚠️ **CRITICAL**：使用任何 shadcn-vue 组件前，必须先通过 `/shadcn-vue` Skill 查找组件和使用规范

### 13.1 强制流程

```
需要 UI 组件
    ↓
/shadcn-vue 查找组件和使用规范
    ↓
获取正确的组件名称、API、示例
    ↓
在代码中使用
```

### 13.2 本次实施涉及的 shadcn-vue 组件

| 组件 | 用途 | Skill 查询示例 |
|------|------|---------------|
| **Button** | 操作按钮 | `/shadcn-vue Button 组件` |
| **Input** | 搜索框 | `/shadcn-vue Input 组件` |
| **Pagination** | 分页 | `/shadcn-vue Pagination 组件` |
| **AlertDialog** | 确认对话框 | `/shadcn-vue AlertDialog 如何使用` |
| **Toast** | 消息提示 | `/shadcn-vue Toast 组件` |

### 13.3 技术壁垒判定（MASTER.md §3.4）

| 组件 | shadcn-vue 是否有 | 技术壁垒判定 | 处理方式 |
|------|------------------|--------------|---------|
| **Select** | ❌ 无 | 允许自定义 | 使用原生 `<select>` 或基于 shadcn-vue 扩展 |
| **Tabs** | ✅ 有 | - | 基于 shadcn-vue Tabs 改造为 ContextTabs |
| **Dialog** | ✅ 有 | - | 直接使用 shadcn-vue Dialog |

**关键规则**：
- ✅ shadcn-vue 无此组件 → 允许自定义
- ✅ 功能无法扩展 → 允许自定义
- ❌ "我觉得自己写更好" → 不允许

---

## 十四、DataTable 组件完整性检查（list-page.md §3.0）

### 14.1 已支持功能

| 功能 | 状态 | 实现方式 |
|------|------|---------|
| **自定义单元格模板** | ✅ 已支持 | `#cell-{key}` slot |
| **分页** | ✅ 已支持 | `page`, `pageSize`, `total` props |
| **加载状态** | ✅ 已支持 | `loading` prop + LoadingSkeleton |
| **空状态** | ✅ 已支持 | `emptyTitle` prop + EmptyState |

### 14.2 需验证功能

| 功能 | 验证项 | 状态 |
|------|-------|------|
| **行高** | `44px`（自适应） | ⬜ 待验证 |
| **表头背景** | `#F1F5FD` | ⬜ 待验证 |
| **表头固定** | `position: sticky` | ⬜ 待验证 |
| **Hover 背景** | `#EEF2FF` | ⬜ 待验证 |
| **行分割线** | `#E4ECFC` | ⬜ 待验证 |

### 14.3 移动端适配检查

| 功能 | 验证项 | 状态 |
|------|-------|------|
| **横向滚动** | 允许表格横向滚动 | ⬜ 待验证 |
| **简化列数** | 移动端仅显示核心列 | ⬜ 待验证 |
| **Touch Target** | 行高 ≥ 44px | ⬜ 待验证 |

---

## 十五、FilterPanel Select 组件技术壁垒判定（MASTER.md §3.4）

### 15.1 技术壁垒分析

| 壁垒类型 | 说明 | 是否允许自定义 |
|----------|------|----------------|
| **shadcn-vue 无此组件** | shadcn-vue 没有 Select 组件 | ✅ 允许 |

### 15.2 处理方案

**方案 A（推荐）**：使用原生 `<select>`
- ✅ 简单、无依赖
- ✅ 原生支持移动端键盘
- ❌ 样式自定义受限

**方案 B**：基于 shadcn-vue Popover + Command 扩展
- ✅ 完全自定义样式
- ✅ 支持搜索、分组
- ❌ 开发成本高

**推荐**：Phase 0 使用方案 A（原生 select），Phase 4 视需求升级为方案 B

---

## 十六、补充验收清单

### 16.1 功能验收（补充）

| 页面 | 测试项 | 状态 |
|------|-------|------|
| **所有页面** | 移动端布局正常（375px / 768px / 1024px） | ⬜ |
| **所有页面** | Touch Target ≥ 44px（移动端） | ⬜ |
| **所有页面** | Safe Areas 避开 notch / 手势区域 | ⬜ |
| **所有页面** | Focus ring 可见（键盘导航） | ⬜ |
| **所有页面** | prefers-reduced-motion 生效 | ⬜ |

### 16.2 设计规范验收（补充）

| 检查项 | Token | 状态 |
|--------|-------|------|
| **移动端 input 字号 ≥ 16px** | `$wolf-font-size-body-mobile-v2` | ⬜ |
| **Focus ring 宽度 2px** | `$wolf-focus-ring-width-v2` | ⬜ |
| **Focus ring 偏移 2px** | `$wolf-focus-ring-offset-v2` | ⬜ |
| **动画时长 150ms** | `$wolf-transition-v2` | ⬜ |
| **Reduced motion 支持** | `$wolf-reduced-motion-duration-v2` | ⬜ |
| **暗色模式对比度独立验证** | - | ⬜ |

### 16.3 无障碍验收（补充）

| 检查项 | WCAG 章节 | 状态 |
|--------|----------|------|
| **Focus Visible** | 2.4.7 | ⬜ |
| **对比度 4.5:1** | 1.4.3 | ⬜ |
| **aria-label（图标按钮）** | 4.1.2 | ⬜ |
| **语义化标签** | 1.3.1 | ⬜ |
| **Tab 顺序正确** | 2.4.3 | ⬜ |

---

**版本：V1.1（补充移动端、无障碍、暗色模式、性能规范） | 最后更新：2026-07-09**