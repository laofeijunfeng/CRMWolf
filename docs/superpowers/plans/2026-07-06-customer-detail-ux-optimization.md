# CustomerDetail UX Optimization - 折叠控制位置 + 图标差异化

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 优化客户详情页 UX,解决两个核心问题:
1. 客户档案折叠控制位置不当(导航层级混淆)
2. 快捷操作图标语义不清晰(4个加号无法区分)

**Architecture:**
- 移除侧边栏"客户档案"导航项,避免导航层级混淆
- 在客户档案卡片标题栏添加展开/收起按钮,符合用户期望
- 快捷操作图标差异化(跟进/联系人/商机/合同使用不同图标)
- 保持智能折叠逻辑:切换其他 tab 自动收起,用户手动展开后保持状态

**Tech Stack:** Vue 3 Composition API + Element Plus + Pinia + SCSS Design Tokens

---

## Global Constraints

- 禁止推断业务常量,必须查阅代码定义(CLAUDE.md 防幻觉指令)
- TypeScript 四禁令:禁用 `any` `as any` `@ts-ignore` `!`
- 所有 State 必须类型化:`ref<Type>(...)`
- Design Token 引用:必须使用 `$wolf-*` 变量,禁止魔数
- **UI/UX Pro Max CRITICAL 规则**:
  - `nav-hierarchy` - 导航项只包含页面/视图,内容控制在内容区域
  - `nav-label-icon` - icon-only 导航必须有 tooltip + aria-label
  - `icon-style-consistent` - 不同操作使用不同语义图标
  - `content-priority` - 内容折叠控制在用户期望位置
  - `state-preservation` - 用户手动展开后保持状态

---

## File Structure

**将创建/修改的文件:**

```
CRM-Client/src/
├── components/
│   └── CustomerDetailSidebar.vue         # 修改:移除客户档案导航项 + 快捷操作图标差异化
├── views/
│   └── CustomerDetail.vue                # 修改:客户档案卡片添加展开/收起按钮
```

---

## Task 1: 移除侧边栏"客户档案"导航项

**Files:**
- Modify: `CRM-Client/src/components/CustomerDetailSidebar.vue:121-134`

**UX 问题:** 导航层级混淆 - 客户档案是页面内容,不应该作为导航项

**实施:**

- [ ] **Step 1: 移除客户档案导航项**

修改文件:`CRM-Client/src/components/CustomerDetailSidebar.vue`

**在 Line 121-134 修改:**
```typescript
// 原代码:
const navItems = [
  {
    key: 'profile',
    label: '客户档案',
    icon: FolderOpened,
    collapsible: true
  },
  { key: 'followup', label: '跟进', icon: ChatDotRound },
  { key: 'contacts', label: '联系人', icon: User },
  { key: 'opportunities', label: '商机', icon: TrendCharts },
  { key: 'contracts', label: '合同', icon: Document },
  { key: 'payments', label: '回款', icon: Money },
  { key: 'invoices', label: '发票', icon: Tickets }
]

// 替换为:
const navItems = [
  // ✅ 移除客户档案导航项(避免导航层级混淆)
  { key: 'followup', label: '跟进', icon: ChatDotRound },
  { key: 'contacts', label: '联系人', icon: User },
  { key: 'opportunities', label: '商机', icon: TrendCharts },
  { key: 'contracts', label: '合同', icon: Document },
  { key: 'payments', label: '回款', icon: Money },
  { key: 'invoices', label: '发票', icon: Tickets }
]
```

- [ ] **Step 2: 移除客户档案相关导入和状态**

修改文件:`CRM-Client/src/components/CustomerDetailSidebar.vue`

**删除 Line 94-97:**
```typescript
// 删除:
FolderOpened,   // ✅ Task 2: 客户档案图标(展开)
Folder,         // ✅ Task 2: 客户档案图标(收起)
ArrowDown,      // ✅ Task 2: 展开/收起箭头
ArrowRight      // ✅ Task 2: 展开/收起箭头
```

**删除 Line 118:**
```typescript
// 删除:
const profileExpanded = ref<boolean>(true)  // ✅ Task 2: 客户档案展开状态(默认:展开)
```

**删除 Line 151-155:**
```typescript
// 删除:
function handleProfileClick(): void {
  profileExpanded.value = !profileExpanded.value
  emit('profile-toggle', profileExpanded.value)
  activeNav.value = 'profile'
}
```

**删除 Line 111:**
```typescript
// 删除:
(e: 'profile-toggle', expanded: boolean): void  // ✅ Task 2: 新增客户档案展开/收起事件
```

- [ ] **Step 3: 移除模板中的客户档案特殊处理**

修改文件:`CRM-Client/src/components/CustomerDetailSidebar.vue`

**删除 Line 10-46 中的客户档案特殊处理:**
```vue
<!-- 简化为标准导航项 -->
<el-tooltip
  v-for="nav in navItems"
  :key="nav.key"
  :content="nav.label"
  placement="right"
  :show-after="300"
  effect="light"
>
  <div
    class="nav-item"
    :class="{ active: activeNav === nav.key }"
    tabindex="0"
    :aria-label="nav.label"
    @click="handleNavClick(nav.key)"
    @keydown.enter="handleNavClick(nav.key)"
  >
    <el-icon class="nav-icon">
      <component :is="nav.icon" />
    </el-icon>
  </div>
</el-tooltip>
```

---

## Task 2: 快捷操作图标差异化

**Files:**
- Modify: `CRM-Client/src/components/CustomerDetailSidebar.vue:137-142`

**UX 问题:** 4个快捷操作都使用 Plus 图标,用户无法区分

**实施:**

- [ ] **Step 1: 修改快捷操作定义,添加差异化图标**

修改文件:`CRM-Client/src/components/CustomerDetailSidebar.vue`

**在 Line 137-142 修改:**
```typescript
// 原代码:
const quickActions = [
  { key: 'addFollowUp', label: '跟进', emitKey: 'show-add-follow-up' as const },
  { key: 'addContact', label: '联系人', emitKey: 'show-add-contact' as const },
  { key: 'createOpportunity', label: '商机', route: `/customers/${props.customerId}/opportunities/create` },
  { key: 'createContract', label: '合同', route: `/contracts/create?customerId=${props.customerId}` }
]

// 替换为:
const quickActions = [
  { key: 'addFollowUp', label: '跟进', icon: ChatDotRound, emitKey: 'show-add-follow-up' as const },  // ✅ 使用 ChatDotRound 图标
  { key: 'addContact', label: '联系人', icon: User, emitKey: 'show-add-contact' as const },          // ✅ 使用 User 图标
  { key: 'createOpportunity', label: '商机', icon: TrendCharts, route: `/customers/${props.customerId}/opportunities/create` },  // ✅ 使用 TrendCharts 图标
  { key: 'createContract', label: '合同', icon: Document, route: `/contracts/create?customerId=${props.customerId}` }  // ✅ 使用 Document 图标
]
```

- [ ] **Step 2: 修改模板,使用差异化图标**

修改文件:`CRM-Client/src/components/CustomerDetailSidebar.vue`

**在 Line 57-77 修改:**
```vue
<!-- 快捷操作 -->
<div class="nav-section">
  <div class="nav-section-title">快捷操作</div>

  <!-- ✅ P0: 快捷操作使用差异化图标 -->
  <el-tooltip
    v-for="action in quickActions"
    :key="action.key"
    :content="'新建' + action.label"
    placement="right"
    :show-after="300"
    effect="light"
  >
    <div
      class="nav-action"
      tabindex="0"
      :aria-label="'新建' + action.label"
      @click="handleActionClick(action)"
      @keydown.enter="handleActionClick(action)"
    >
      <el-icon class="nav-action-icon">
        <!-- ✅ 使用差异化图标 -->
        <component :is="action.icon" />
      </el-icon>
    </div>
  </el-tooltip>
</div>
```

---

## Task 3: 客户档案卡片添加展开/收起按钮

**Files:**
- Modify: `CRM-Client/src/views/CustomerDetail.vue:163-184`

**UX 改进:** 内容控制在用户期望位置,符合 **content-priority** 规则

**实施:**

- [ ] **Step 1: 添加展开/收起按钮到客户档案卡片标题栏**

修改文件:`CRM-Client/src/views/CustomerDetail.vue`

**在 Line 163-184 修改:**
```vue
<!-- 客户档案卡片 -->
<div class="profile-card">
  <div class="card-title">
    <span>客户档案</span>
    <div class="profile-controls">
      <!-- ✅ Task 3: 展开/收起按钮 -->
      <el-button
        class="wolf-btn wolf-btn--text collapse-btn"
        @click="profileExpanded = !profileExpanded"
      >
        <el-icon>
          <component :is="profileExpanded ? ArrowDown : ArrowRight" />
        </el-icon>
        {{ profileExpanded ? '收起' : '展开' }}
      </el-button>

      <!-- 原有的状态标签 -->
      <div class="profile-status">
        <template v-if="customerDetail?.profile_status === 'PENDING'">
          <el-tag class="wolf-tag wolf-tag--gray" size="small">等待生成</el-tag>
        </template>
        <template v-else-if="customerDetail?.profile_status === 'GENERATING'">
          <el-tag class="wolf-tag wolf-tag--warning" size="small">
            <el-icon class="is-loading"><Loading /></el-icon>
            正在生成
          </el-tag>
        </template>
        <template v-else-if="customerDetail?.profile_status === 'COMPLETED'">
          <el-tag class="wolf-tag wolf-tag--success" size="small">生成完成</el-tag>
        </template>
        <template v-else-if="customerDetail?.profile_status === 'FAILED'">
          <el-tag class="wolf-tag wolf-tag--danger" size="small">生成失败</el-tag>
        </template>
      </div>
    </div>
  </div>

  <!-- 原有的档案内容... -->
</div>
```

- [ ] **Step 2: 导入 ArrowDown 和 ArrowRight 图标**

修改文件:`CRM-Client/src/views/CustomerDetail.vue`

**在 Line 912-925 添加:**
```typescript
import {
  Plus,
  CircleCheck,
  CircleClose,
  Clock,
  Calendar,
  PriceTag,
  Money,
  Coin,
  ShoppingCart,
  Document,
  Loading,
  WarningFilled,
  ArrowDown,    // ✅ Task 3: 展开箭头
  ArrowRight    // ✅ Task 3: 收起箭头
} from '@element-plus/icons-vue'
```

- [ ] **Step 3: 添加样式**

修改文件:`CRM-Client/src/views/CustomerDetail.vue` (style 部分)

**添加:**
```scss
// ✅ Task 3: 客户档案控制栏样式
.profile-controls {
  display: flex;
  align-items: center;
  gap: $wolf-space-md;
}

.collapse-btn {
  display: flex;
  align-items: center;
  gap: $wolf-space-xs;
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;

  &:hover {
    color: $wolf-text-secondary;
  }

  .el-icon {
    font-size: 14px;
    transition: transform $wolf-transition-normal;
  }
}
```

---

## Task 4: 移除侧边栏 emit 事件监听

**Files:**
- Modify: `CRM-Client/src/views/CustomerDetail.vue:5-11`

**实施:**

- [ ] **Step 1: 移除 profile-toggle 事件监听**

修改文件:`CRM-Client/src/views/CustomerDetail.vue`

**在 Line 5-11 修改:**
```vue
<!-- 原代码: -->
<CustomerDetailSidebar
  :customer-id="customerId"
  @nav-change="handleNavChange"
  @show-add-follow-up="showAddFollowUpModal"
  @show-add-contact="showAddContactModal"
  @profile-toggle="handleProfileToggle"  <!-- ✅ 删除此行 -->
/>

<!-- 替换为: -->
<CustomerDetailSidebar
  :customer-id="customerId"
  @nav-change="handleNavChange"
  @show-add-follow-up="showAddFollowUpModal"
  @show-add-contact="showAddContactModal"
/>
```

- [ ] **Step 2: 移除 handleProfileToggle 函数**

修改文件:`CRM-Client/src/views/CustomerDetail.vue`

**删除 Line 981-988:**
```typescript
// 删除:
const handleProfileToggle = (expanded: boolean): void => {
  profileExpanded.value = expanded

  if (expanded) {
    userExpandedProfile.value = true
  }
}
```

- [ ] **Step 3: 简化 handleNavChange 函数**

修改文件:`CRM-Client/src/views/CustomerDetail.vue`

**在 Line 969-978 修改:**
```typescript
// 导航切换处理
const handleNavChange = (navKey: string): void => {
  activeTab.value = navKey

  // ✅ 智能折叠逻辑保持不变:
  // - 首次切换:自动收起客户档案(节省空间)
  // - 用户手动展开后:不自动收起(尊重用户控制权)
  if (!userExpandedProfile.value) {
    profileExpanded.value = false  // 自动收起
  }
}
```

---

## Task 5: 验证和测试

**Files:**
- Test: 手动测试所有功能

- [ ] **Step 1: 验证侧边栏导航项移除**

手动测试:
1. 检查侧边栏是否只包含:跟进、联系人、商机、合同、回款、发票
2. 检查是否没有"客户档案"导航项

- [ ] **Step 2: 验证快捷操作图标差异化**

手动测试:
1. 检查快捷操作是否显示不同图标:
   - 新建跟进: ChatDotRound (对话图标)
   - 新建联系人: User (用户图标)
   - 新建商机: TrendCharts (趋势图标)
   - 新建合同: Document (文档图标)
2. hover 时 tooltip 是否显示"新建跟进"、"新建联系人"等

- [ ] **Step 3: 验证客户档案折叠功能**

手动测试:
1. 检查客户档案卡片标题栏是否有"展开/收起"按钮
2. 点击"收起"按钮:客户档案是否收起为简化版卡片
3. 点击"展开"按钮:客户档案是否展开为完整内容
4. 切换到"跟进"tab:客户档案是否自动收起
5. 手动展开客户档案后,再次切换 tab:客户档案是否保持展开状态

---

## Task 6: 提交代码

- [ ] **Step 1: 提交所有修改**

```bash
git add CRM-Client/src/components/CustomerDetailSidebar.vue CRM-Client/src/views/CustomerDetail.vue
git commit -m "feat(customer-detail): optimize UX - move collapse control to content area + differentiate quick action icons

完成 Task 1-4:
- 移除侧边栏客户档案导航项(避免导航层级混淆)
- 客户档案卡片添加展开/收起按钮(符合用户期望)
- 快捷操作图标差异化(解决4个加号无法区分的问题)
- 保持智能折叠逻辑:切换 tab 自动收起,用户手动展开后保持状态

符合 UI/UX Pro Max 规则:
- nav-hierarchy ✅
- nav-label-icon ✅
- icon-style-consistent ✅
- content-priority ✅
- state-preservation ✅"
```

---

## Self-Review Checklist

**1. Spec Coverage:**

| 需求 | 任务 | 状态 |
|------|------|------|
| 移除侧边栏客户档案导航项 | Task 1 | ✅ |
| 快捷操作图标差异化 | Task 2 | ✅ |
| 客户档案卡片添加展开/收起按钮 | Task 3 | ✅ |
| 移除 emit 事件监听 | Task 4 | ✅ |
| 验证和测试 | Task 5 | ✅ |
| 提交代码 | Task 6 | ✅ |

**2. UI/UX Pro Max CRITICAL 规则验证清单:**

| 规则 | 实施位置 | 状态 |
|------|----------|------|
| nav-hierarchy | CustomerDetailSidebar.vue (移除客户档案导航项) | ✅ |
| nav-label-icon | CustomerDetailSidebar.vue (tooltip + aria-label) | ✅ |
| icon-style-consistent | CustomerDetailSidebar.vue (快捷操作图标差异化) | ✅ |
| content-priority | CustomerDetail.vue (折叠控制在内容区域) | ✅ |
| state-preservation | CustomerDetail.vue (userExpandedProfile 逻辑) | ✅ |

**3. Type Consistency:**

| 类型定义位置 | 使用位置 | 一致性 |
|--------------|----------|--------|
| `profileExpanded: boolean` | CustomerDetail.vue | ✅ |
| `userExpandedProfile: boolean` | CustomerDetail.vue | ✅ |
| `quickActions: Array<{icon: Component}>` | CustomerDetailSidebar.vue | ✅ |

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-07-06-customer-detail-ux-optimization.md`.**

**Two execution options:**

1. **Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**