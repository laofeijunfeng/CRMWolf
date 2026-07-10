# CRMWolf 页面结构规范 - 列表页

**适用页面**：线索管理、客户管理、商机管理、合同管理、回款管理、发票管理

---

## 一、页面组成（三层结构）

### 1.1 导航层级

```
Sidebar（一级导航，固定）
└── TopBar（顶部栏，固定）
    └── Table Area（内容区域，可滚动）
```

### 1.2 组件清单

| 位置 | 组件 | 高度 | 说明 |
|------|------|------|------|
| **左侧** | `SidebarV2` | 100vh | 全局菜单，固定不动 |
| **顶部** | `TopBarV2` | 56px | 包含页面标题、操作按钮、审批铃铛 |
| **内容** | `TableV2` + Filters | 自适应 | 表格 + 搜索栏 |

---

## 二、TopBar 布局（列表页）

### 2.1 三段式布局

| 区域 | 内容 | 示例 |
|------|------|------|
| **左侧（48px）** | 空白或返回按钮 | 无（列表页无返回） |
| **中间（居中）** | 页面标题 | "客户管理" |
| **右侧（自适应）** | 操作按钮 + 审批铃铛 | "新建客户" + "导出" + 🔔 |

### 2.2 操作按钮规范

| 按钮 | 类型 | 优先级 | 位置 |
|------|------|--------|------|
| **新建** | Primary | 最高 | 右侧最左 |
| **导出** | Default | 中等 | 新建按钮右侧 |
| **审批铃铛** | Icon | 低 | 最右侧（固定） |

---

## 三、表格区域布局

### 3.0 DataTable 组件（强制使用）

> ⚠️ **强制要求**：所有列表页必须使用 `DataTable` 组件，确保样式统一

**组件位置**：`src/components/crmwolf/DataTable.vue`

**核心特性**：

| 特性 | 说明 |
|------|------|
| **固定首列和尾列** | 默认固定左侧1列、右侧1列，中间列横向滚动 |
| **固定高度** | 默认 `calc(100vh - 200px)`，可自定义 |
| **内部滚动** | 表格内容区可滚动，表头固定 |
| **分页固定** | 底部分页栏固定，不随内容滚动 |
| **加载状态** | 内置 LoadingSkeleton |
| **空状态** | 内置 EmptyState |

**Props**：

| 属性 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `columns` | `Column[]` | ✅ | - | 列定义 |
| `data` | `Record<string, unknown>[]` | ✅ | - | 数据源 |
| `total` | `number` | ✅ | - | 总条数 |
| `page` | `number` | ✅ | - | 当前页码 |
| `pageSize` | `number` | ✅ | - | 每页条数 |
| `loading` | `boolean` | ❌ | `false` | 加载状态 |
| `height` | `string` | ❌ | `calc(100vh - 200px)` | 卡片高度 |
| `emptyTitle` | `string` | ❌ | `暂无数据` | 空状态标题 |
| `fixedLeftCount` | `number` | ❌ | `1` | 默认固定左侧列数 |
| `fixedRightCount` | `number` | ❌ | `1` | 默认固定右侧列数 |

**Column 配置**：

| 属性 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `key` | `string` | ✅ | 列标识（用于 slot 和数据绑定） |
| `title` | `string` | ✅ | 列标题 |
| `width` | `string` | ❌ | 列宽度（如 `"150px"`） |
| `align` | `'left' \| 'center' \| 'right'` | ❌ | 对齐方式 |
| `fixed` | `'left' \| 'right'` | ❌ | 固定列位置（优先级高于 fixedLeftCount/fixedRightCount） |

**Events**：

| 事件 | 参数 | 说明 |
|------|------|------|
| `update:page` | `number` | 页码变化 |
| `update:pageSize` | `number` | 每页条数变化 |
| `row-click` | `row` | 行点击 |

**Slots**：

| 插槽 | 参数 | 说明 |
|------|------|------|
| `cell-{key}` | `{ row, value }` | 自定义单元格 |

**固定列配置示例**：

```vue
<script setup lang="ts">
import { DataTable } from '@/components/crmwolf'

// 方式一：默认配置（固定左侧1列、右侧1列）
const columns = [
  { key: 'application_number', title: '申请单号', width: '220px' },  // 自动固定左侧
  { key: 'customer_name', title: '客户名称', width: '150px' },
  { key: 'contract_name', title: '合同名称', width: '180px' },
  { key: 'invoice_type', title: '发票类型', width: '150px' },
  { key: 'invoice_amount', title: '开票金额', width: '130px' },
  { key: 'actions', title: '操作', width: '140px' },  // 自动固定右侧
]
// 无需额外配置，默认固定首列和尾列

// 方式二：自定义固定列数
<DataTable
  :columns="columns"
  :fixed-left-count="2"  // 固定左侧2列
  :fixed-right-count="1"
/>

// 方式三：显式指定固定列（最高优先级）
const columns = [
  { key: 'id', title: 'ID', width: '80px', fixed: 'left' },
  { key: 'name', title: '名称', width: '150px' },  // 不固定
  { key: 'status', title: '状态', width: '100px', fixed: 'right' },
  { key: 'actions', title: '操作', width: '120px', fixed: 'right' },
]
</script>
```

**使用示例**：

```vue
<script setup lang="ts">
import { DataTable } from '@/components/crmwolf'

const columns = [
  { key: 'name', title: '客户名称' },
  { key: 'contact', title: '联系人' },
  { key: 'phone', title: '联系电话' },
  { key: 'status', title: '状态', align: 'center' },
  { key: 'actions', title: '操作', align: 'center', width: '120px' },
]

const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 100
})
</script>

<template>
  <DataTable
    :columns="columns"
    :data="tableData"
    :page="pagination.page"
    :page-size="pagination.pageSize"
    :total="pagination.total"
    @update:page="pagination.page = $event"
    @row-click="handleRowClick"
  >
    <!-- 自定义单元格 -->
    <template #cell-status="{ row }">
      <span :class="['status-badge', `status-${row.status}`]">
        {{ getStatusText(row.status) }}
      </span>
    </template>

    <template #cell-actions="{ row }">
      <Button size="sm" @click.stop="handleEdit(row)">编辑</Button>
    </template>
  </DataTable>
</template>
```

---

### 3.1 搜索/筛选栏（表格上方）

| 元素 | 高度 | 位置 |
|------|------|------|
| **搜索框** | 32px | 左侧 |
| **筛选下拉** | 32px | 搜索框右侧 |
| **高级筛选按钮** | 32px | 最右侧 |

### 3.2 表格规范

| 属性 | 值 |
|------|-----|
| **行高** | 44px（自适应，内容换行时撑高） |
| **表头背景** | `#F1F5FD` |
| **表头字号** | 13px |
| **表头字重** | 600 |
| **表头文字色** | `#64748B` |
| **行分割线** | `#E4ECFC`（极淡，视觉上近乎无） |
| **Hover 背景** | `#EEF2FF` |

### 3.3 表头对齐规则

| 列类型 | 对齐方式 | 示例 |
|--------|---------|------|
| **文字列** | 左对齐 | 客户名称、联系人 |
| **数字列** | 右对齐 | 金额、数量 |
| **状态列** | 居中 | 状态 Badge |
| **操作列** | 居中 | 编辑、删除按钮 |

### 3.4 操作列规范

| 按钮 | 尺寸 | 间距 |
|------|------|------|
| **编辑** | 24px（sm） | 8px |
| **删除** | 24px（sm） | 8px |

---

## 四、布局实现规范

### 4.1 页面容器布局

列表页应遵循 AppLayout 的布局架构（详见 MASTER.md §6.6）：

```scss
// 列表页容器（如 Leads.vue）
.leads-page {
  padding: $wolf-page-padding-v2;  // 24px
  background: $wolf-bg-page-v2;
  display: flex;
  flex-direction: column;
  gap: $wolf-section-gap-v2;  // 24px - SearchCard 与 DataTable 的间距
  min-height: 0;  // 让 flexbox 控制高度
  flex: 1;  // 继承父容器高度
}
```

**关键要点：**

1. ✅ 使用 `padding: 24px`（AppLayout 已提供顶部 16px 系统级间距）
2. ✅ 使用 `gap: 24px` 分隔 SearchCard 和 DataTable
3. ✅ 使用 `min-height: 0` + `flex: 1` 管理 flexbox 高度
4. ❌ 禁止使用 `min-height: calc(100vh - XXpx)` 固定高度计算

### 4.2 高度管理

**AppLayout 层级：**
- 使用 `100dvh` (dynamic viewport height)
- 提供 `padding-top: 16px` 系统级间距

**页面组件层级：**
- 使用 `min-height: 0` + `flex: 1` 继承高度
- 禁止硬编码高度计算

**DataTable 组件：**
- 使用固定高度 `calc(100vh - 200px)` 或自定义 `height` prop
- 内部滚动，表头固定

### 4.3 间距计算示例

```
AppLayout.main-content (无 padding-top)
├── TopBar (56px, sticky, top: 0)  ← 紧贴顶部
└── Leads.vue
    ├── padding-top: 24px  ← 与 TopBar 的间距
    ├── SearchCard
    ├── gap: 24px  ← 组件间距
    └── DataTable (flex: 1, 填充剩余空间)
```

### 4.4 常见错误

```scss
// ❌ 错误 1：硬编码高度计算
.leads-page {
  min-height: calc(100vh - 48px);  // 错误的值
}

// ❌ 错误 2：缺少 gap 属性
.leads-page {
  display: flex;
  flex-direction: column;
  // SearchCard 和 DataTable 贴在一起
}

// ❌ 错误 3：移除所有 padding
.leads-page {
  padding: 0;  // 页面内容贴边
}
```

---

## 五、状态 Badge 规范

### 4.1 客户状态

| 状态 | 背景色 | 文字色 | 文字 |
|------|--------|--------|------|
| **跟进中** | `#DCFCE7` | `#166534` | 跟进中 |
| **已成交** | `#DCFCE7` | `#166534` | 已成交 |
| **已流失** | `#FEE2E2` | `#991B1B` | 已流失 |
| **公海池** | `#F1F5FD` | `#64748B` | 公海 |

### 4.2 审批状态

| 状态 | 背景色 | 文字色 | 文字 |
|------|--------|--------|------|
| **待审批** | `#FEF3C7` | `#92400E` | 待审批 |
| **审批中** | `#FEF3C7` | `#92400E` | 审批中 |
| **已通过** | `#DCFCE7` | `#166534` | 已通过 |
| **已驳回** | `#FEE2E2` | `#991B1B` | 已驳回 |

---

## 五、分页规范

### 5.1 分页位置

- **位置**：表格底部，右对齐
- **组件**：Element Plus Pagination

### 5.2 分页样式

| 属性 | 值 |
|------|-----|
| **字号** | 13px |
| **按钮圆角** | 6px |
| **总条数显示** | 左侧，"共 100 条" |

---

## 六、空状态规范

### 6.1 空状态设计

| 元素 | 说明 |
|------|------|
| **图标** | 大号空状态图标（48px） |
| **文字** | "暂无客户数据" |
| **引导按钮** | "新建第一个客户"（Primary 按钮） |

---

## 七、响应式布局

### 7.1 断点适配

| 断点 | 侧边栏 | TopBar | 表格 |
|------|--------|--------|------|
| **xs（375px）** | 隐藏 | 显示（56px） | 全宽 |
| **sm（768px）** | 隐藏 | 显示（56px） | 全宽 |
| **md（1024px）** | 显示（220px） | 显示（56px） | 内容宽度 = viewport - 220px |
| **lg（1440px）** | 显示（220px） | 显示（56px） | 内容宽度 = viewport - 220px |

---

## 八、交互动效

### 8.1 Hover 效果

| 元素 | Hover 效果 | 过渡时间 |
|------|----------|---------|
| **表格行** | 背景 `#EEF2FF` | 150ms |
| **操作按钮** | 背景 + 边框变化 | 150ms |
| **状态 Badge** | 无 hover（静态） | 无 |

### 8.2 点击反馈

| 元素 | 反馈 |
|------|------|
| **表格行** | 点击后选中（背景 `#F1F5FD`） |
| **操作按钮** | 点击后 loading（按钮禁用 + spinner） |

---

## 九、性能优化

### 9.1 虚拟化列表

- **阈值**：超过 50 条数据启用虚拟化
- **库**：`vue-virtual-scroller`

### 9.2 分页加载

- **默认**：每页 20 条
- **可选**：10 / 20 / 50 / 100

---

## 十、代码示例

### 10.1 页面结构（伪代码）

```vue
<template>
  <div class="list-page">
    <!-- 左侧菜单 -->
    <SidebarV2 />
    
    <!-- 顶部栏 -->
    <TopBarV2>
      <template #center>
        <h1>客户管理</h1>
      </template>
      <template #right>
        <ButtonV2 variant="primary">新建客户</ButtonV2>
        <ButtonV2 variant="default">导出</ButtonV2>
        <ApprovalIcon :count="5" />
      </template>
    </TopBarV2>
    
    <!-- 内容区域 -->
    <main class="content-area">
      <!-- 搜索栏 -->
      <div class="search-bar">
        <InputV2 placeholder="搜索客户名称" />
        <SelectV2 placeholder="筛选状态" />
      </div>
      
      <!-- 表格 -->
      <TableV2 :data="customers">
        <el-table-column label="客户名称" prop="name" />
        <el-table-column label="联系人" prop="contact" />
        <el-table-column label="金额" prop="amount" align="right" />
        <el-table-column label="状态" prop="status">
          <template #default="{ row }">
            <StatusBadge :status="row.status" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" align="center">
          <template #default="{ row }">
            <ButtonV2 size="sm" @click="edit(row)">编辑</ButtonV2>
            <ButtonV2 size="sm" variant="danger" @click="delete(row)">删除</ButtonV2>
          </template>
        </el-table-column>
      </TableV2>
      
      <!-- 分页 -->
      <Pagination :total="100" />
    </main>
  </div>
</template>
```

---

**适用页面列表**：
- 线索管理（Leads.vue）
- 客户管理（Customers.vue）
- 商机管理（Opportunities.vue）
- 合同管理（Contracts.vue）
- 回款管理（Payments.vue）
- 发票管理（Invoices.vue）

**版本：V2 | 最后更新：2026-07-08**