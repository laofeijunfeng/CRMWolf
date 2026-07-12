# 客户详情抽屉设计文档

**版本**: V1.0  
**日期**: 2026-07-10  
**状态**: 待审阅

---

## 一、设计背景

### 1.1 问题陈述

当前客户详情页（`CustomerDetail.vue`）是一个 **全页面视图**（2700+ 行代码），存在以下问题：

- **技术栈落后**：使用 Element Plus + variables.scss（旧设计系统）
- **上下文断裂**：查看详情需跳转页面，打断用户操作流程
- **维护成本高**：代码量大，组件耦合严重

### 1.2 目标

将客户详情页改为 **抽屉组件**，类似线索详情抽屉（`LeadDetailSheet.vue`），实现：

- ✅ 保持上下文：在列表页直接打开抽屉，无需跳转
- ✅ 技术栈升级：迁移到 shadcn-vue + variables-v2.scss（新设计系统）
- ✅ 代码简化：拆分为独立组件，降低维护成本

---

## 二、设计方案

### 2.1 核心决策

| 决策项 | 方案 |
|--------|------|
| **内容组织** | 全部放入抽屉（7个面板） |
| **导航方式** | 桌面端：左侧 Sidebar；移动端：Select 下拉 |
| **抽屉宽度** | 80% + max-width: 1200px；移动端 95%/100% |
| **客户档案** | 可折叠卡片 |
| **打开机制** | 列表页点击客户名 |
| **Sidebar 样式** | 使用 shadcn-vue Sidebar 组件 |
| **Header 设计** | 客户名 + 状态 + 统计（联系人数） |
| **Footer 设计** | 新建商机（Primary）+ 新建合同（Outline）+ 编辑（Outline） |
| **设计系统** | 全面迁移（shadcn-vue + variables-v2.scss） |

---

## 三、技术架构

### 3.1 组件结构

```
CustomerDetailSheet.vue（新组件）
├── Sheet（shadcn-vue，80%宽度，max-width: 1200px）
│   ├── SheetHeader（客户名 + 状态 + 统计）
│   │   └── 移动端：Select 下拉导航
│   ├── SheetContent（左右布局 → 移动端单栏）
│   │   ├── 左侧：Sidebar（sticky 定位，200px）
│   │   │   └── 使用 shadcn-vue Sidebar 组件
│   │   └── 右侧：ScrollArea（单滚动区域）
│   │       ├── 基本信息卡片
│   │       ├── 热力值卡片
│   │       ├── 客户档案卡片（可折叠）
│   │       └── 内容面板（7个，根据导航切换）
│   └── SheetFooter（编辑 + 新建商机 + 新建合同）
```

### 3.2 文件结构

```
src/views/
├── CustomerDetailSheet.vue          # 主抽屉组件
└── Customers.vue                    # 列表页（修改打开方式）

src/components/
├── CustomerDetailSidebar.vue        # Sidebar 导航组件（复用现有）
├── panels/                          # 内容面板组件
│   ├── FollowUpPanel.vue            # 跟进记录
│   ├── ContactsPanel.vue            # 联系人
│   ├── OpportunitiesPanel.vue       # 商机
│   ├── ContractsPanel.vue           # 合同
│   ├── PaymentsPanel.vue            # 回款
│   ├── InvoicesPanel.vue            # 发票
│   └── LicenseManagement.vue        # License 管理（复用现有）
├── dialogs/                         # 弹窗组件
│   ├── OpportunityFormDialog.vue    # 新建商机弹窗
│   ├── ContractFormDialog.vue       # 新建合同弹窗
│   └── ...
└── ...
```

---

## 四、UI 设计规范

### 4.1 Sheet 宽度

| 断点 | 宽度 |
|------|------|
| **桌面端（≥769px）** | 80%，max-width: 1200px |
| **平板（<768px）** | 95% |
| **手机（<480px）** | 100% |

### 4.2 Header 设计

```vue
<SheetHeader class="p-6 border-b border-wolf-border-default-v2">
  <!-- 桌面端 -->
  <div class="hidden md:flex items-center gap-4">
    <div class="title-avatar">{{ customer.account_name?.charAt(0) }}</div>
    <div class="flex-1">
      <SheetTitle class="text-base font-semibold">{{ customer.account_name }}</SheetTitle>
      <Badge>{{ status }}</Badge>
    </div>
    <div class="text-right">
      <div class="text-xs">联系人数</div>
      <div class="text-base font-semibold">{{ count }} 人</div>
    </div>
  </div>
  
  <!-- 移动端：客户信息 + Select 导航 -->
  <div class="md:hidden">
    <div class="flex items-center gap-4 mb-3">
      <div class="title-avatar">...</div>
      <SheetTitle>{{ customer.account_name }}</SheetTitle>
    </div>
    <Select v-model="activePanel" class="w-full h-12">
      <SelectItem value="followup">跟进记录</SelectItem>
      <!-- 其他导航项 -->
    </Select>
  </div>
</SheetHeader>
```

**关键规范**：
- 客户名称字号：`text-base` (16px)，符合 `$wolf-font-size-title-v2`
- 移动端 Select 高度：48px，符合 ContextTabs 规范

### 4.3 Footer 设计

```vue
<SheetFooter class="p-4 border-t border-wolf-border-default-v2 flex flex-row gap-2">
  <Button variant="default" @click="handleCreateOpportunity">
    <Plus class="w-4 h-4 mr-2" />
    新建商机
  </Button>
  <Button variant="outline" @click="handleCreateContract">
    <Plus class="w-4 h-4 mr-2" />
    新建合同
  </Button>
  <Button variant="outline" @click="handleEdit">
    <Pencil class="w-4 h-4 mr-2" />
    编辑
  </Button>
</SheetFooter>
```

**关键规范**：
- 唯一主 CTA：新建商机（Primary）
- 次要操作：新建合同、编辑（Outline）
- 图标来源：Lucide Icons

### 4.4 内容区布局

```scss
// SheetContent 内部布局
.sheet-content-wrapper {
  display: flex;
  flex-direction: column; // 移动端垂直布局
  height: calc(100vh - 180px);
  overflow-y: auto; // 单滚动区域
  
  @media (min-width: 769px) {
    flex-direction: row; // 桌面端左右布局
  }
}

// 左侧 Sidebar（sticky）
.sidebar-wrapper {
  position: sticky;
  top: 0;
  width: 200px;
  background: $wolf-bg-card-v2;
  z-index: 10;
  
  @media (max-width: 768px) {
    display: none; // 移动端隐藏
  }
}

// 右侧内容区
.content-wrapper {
  flex: 1;
  padding: $wolf-space-lg-v2;
}
```

**关键规范**：
- Sidebar sticky 定位，单滚动区域
- 移动端隐藏 Sidebar，改用 Select 导航

### 4.5 基本信息卡片

```vue
<Card class="info-card">
  <CardContent class="p-0">
    <div class="p-4 border-b border-wolf-border-light-v2">
      <h3 class="text-sm font-semibold">基本信息</h3>
    </div>
    <div class="p-4">
      <div class="attributes-grid">
        <div class="attribute-item">
          <div class="attribute-label">客户来源</div>
          <div class="attribute-value">{{ customer.source || '-' }}</div>
        </div>
        <!-- 更多属性 -->
      </div>
    </div>
  </CardContent>
</Card>
```

**属性网格规范**：
- 列数：xs 1列 / sm 2列 / md+ 3列
- 列间距：`$wolf-space-lg-v2` (24px)
- 行间距：`$wolf-space-md-v2` (16px)
- 标签字号：`$wolf-font-size-caption-v2` (12px)
- 值字号：`$wolf-font-size-body-v2` (14px)

### 4.6 客户档案卡片

```vue
<Card class="profile-card">
  <!-- 可点击头部 -->
  <div class="card-header" @click="profileExpanded = !profileExpanded">
    <h3>客户档案</h3>
    <Button variant="ghost" size="sm">
      <ChevronDown v-if="profileExpanded" />
      <ChevronRight v-else />
    </Button>
    <Badge>{{ status }}</Badge>
  </div>
  
  <!-- 展开内容 -->
  <div v-show="profileExpanded">
    <!-- 生成中状态 -->
    <div v-if="status === 'GENERATING'">
      <div class="generating-animation">...</div>
    </div>
    
    <!-- 生成完成状态 -->
    <div v-if="status === 'COMPLETED'">
      <!-- 属性 + 企业背景 + 主营业务 -->
    </div>
  </div>
</Card>
```

---

## 五、设计系统迁移清单

### 5.1 组件迁移

| Element Plus | shadcn-vue |
|--------------|------------|
| `el-dialog` | `Dialog` + `DialogContent` |
| `el-table` | `Table` + `TableHeader` + `TableRow` + `TableCell` |
| `el-form` | `Form`（VeeValidate） |
| `el-input` | `Input` |
| `el-textarea` | `Textarea` |
| `el-select` | `Select` |
| `el-radio-group` | `RadioGroup` + `RadioGroupItem` |
| `el-switch` | `Switch` |
| `el-button` | `Button` |
| `el-tag` | `Badge` |
| `el-empty` | `Empty` + `EmptyTitle` + `EmptyDescription` |
| `el-progress` | `Progress` |
| `v-loading` | `Skeleton` |

### 5.2 样式迁移

| 旧样式 | 新样式 |
|--------|--------|
| `@use '@/styles/variables.scss'` | `@use '@/styles/variables-v2.scss'` |
| `$wolf-xxx` | `$wolf-xxx-v2` |
| 硬编码颜色 | Design Tokens |

### 5.3 新增组件

| 组件 | 说明 |
|------|------|
| `OpportunityFormDialog.vue` | 新建商机弹窗（参考 LeadFormDialog） |
| `ContractFormDialog.vue` | 新建合同弹窗 |

---

## 六、路由变更

### 6.1 删除路由

```typescript
// 删除
{
  path: 'customers/:id',
  name: 'CustomerDetail',
  component: () => import('@/views/CustomerDetail.vue'),
  meta: { requiresAuth: true }
}
```

### 6.2 保留路由

```typescript
// 保留
{
  path: 'customers/create',
  name: 'CustomerCreate',
  component: () => import('@/views/CustomerEdit.vue'),
  meta: { requiresAuth: true }
},
{
  path: 'customers/:id/edit',
  name: 'CustomerEdit',
  component: () => import('@/views/CustomerEdit.vue'),
  meta: { requiresAuth: true }
}
```

---

## 七、实施步骤

### 7.1 阶段一：创建抽屉骨架

1. 创建 `CustomerDetailSheet.vue`（Sheet 结构）
2. 集成 shadcn-vue Sidebar 组件
3. 实现 Header + Footer 基础结构

### 7.2 阶段二：迁移核心卡片

1. 迁移基本信息卡片
2. 迁移热力值卡片
3. 迁移客户档案卡片（可折叠逻辑）

### 7.3 阶段三：迁移内容面板

1. 创建 7 个面板组件
2. 实现面板切换逻辑
3. 迁移各面板的业务逻辑

### 7.4 阶段四：创建表单弹窗

1. 创建 `OpportunityFormDialog.vue`
2. 创建 `ContractFormDialog.vue`
3. 集成到 Footer 操作

### 7.5 阶段五：修改列表页 + 清理

1. 修改 `Customers.vue`（点击客户名打开抽屉）
2. 删除旧路由
3. 删除 `CustomerDetail.vue`（旧组件）

---

## 八、验证清单

### 8.1 设计规范验证

- [x] 使用 `variables-v2.scss`
- [x] 使用 `$wolf-xxx-v2` 变量
- [x] 使用 shadcn-vue 组件
- [x] Footer 仅一个 Primary CTA
- [x] 移动端无横向滚动

### 8.2 ui-ux-pro-max 验证

- [x] Sidebar sticky，单滚动区域
- [x] 移动端使用 Select（非 Tabs 横向滚动）
- [x] 图标使用 Lucide（非 Emoji）
- [x] 加载状态使用 Skeleton/Shimmer
- [x] 动画时长 150-300ms

### 8.3 TypeScript 规范

- [ ] 禁用 `any`、`as any`、`@ts-ignore`、`!`
- [ ] Props/Emits 类型化
- [ ] API 响应 Zod 校验

---

## 九、风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| **工作量估算不足** | 延期 | 分阶段实施，每阶段独立验证 |
| **设计系统迁移遗漏** | 视觉不一致 | 代码审查 + Stylelint 校验 |
| **业务逻辑丢失** | 功能缺失 | 完整迁移测试用例 |
| **性能问题** | 抽屉卡顿 | 懒加载面板组件 |

---

## 十、附录

### 10.1 参考资料

- 设计规范：`CRM-Docs/design-system/README.md`
- 详情页规范：`CRM-Docs/design-system/pages/detail-page.md`
- shadcn-vue：https://www.shadcn-vue.com/
- Lucide Icons：https://lucide.dev/

### 10.2 相关文档

- 线索详情抽屉：`src/views/LeadDetailSheet.vue`
- 客户详情页（旧）：`src/views/CustomerDetail.vue`
- 客户列表页：`src/views/Customers.vue`

---

**文档版本**: V1.0  
**最后更新**: 2026-07-10