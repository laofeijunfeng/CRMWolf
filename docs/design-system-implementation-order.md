# CRMWolf 设计系统实施顺序决策指南

## 🎯 核心问题

**你的问题**：是先建立基础组件库（按钮、表格、tab、配色体系），然后再迁移，还是直接开始迁移？

**正确答案**：**先建立基础组件库，再迁移**。这是业界最佳实践，避免大爆炸式重构。

---

## 📊 决策树：两种策略对比

| 策略 | 说明 | 优点 | 缺点 | 适用场景 |
|------|------|------|------|---------|
| **策略 A：基础先行** | 先建 Design Tokens + 基础组件库，再迁移页面 | ✅ 风险可控<br>✅ 新组件充分测试<br>✅ 设计系统先验证 | ⚠️ 初期工作量大<br>⚠️ 需要耐心 | **推荐**（你的情况） |
| **策略 B：直接迁移** | 直接在页面中创建新组件，边迁移边完善 | ✅ 立即可见效果<br>✅ 快速反馈 | ❌ 组件质量不稳定<br>❌ 可能重复返工<br>❌ 样式不统一风险高 | ❌ 不推荐（风险高） |

---

## 🚀 推荐顺序：基础先行策略

### **Phase 0: 基础设施准备（2-3周）**

这是必须先做的，**不能跳过**：

#### 0.1 建立 Design Tokens（第1周）

**必须先做的 3 个文件**：

| 文件 | 内容 | 工作量 | 输出 |
|------|------|--------|------|
| **variables-v2.scss** | 颜色、圆角、间距、阴影 Tokens | 2天 | 设计系统基础 |
| **CRM-Docs/design-system/README.md** | 设计规则文档（UI/UX Pro Max生成） | 1天 | 唯一规则来源 |
| **element-plus-theme-v2.scss** | Element Plus 主题适配 | 1天 | UI框架适配 |

**关键原则**：
- ✅ 所有新变量必须以 `-v2` 结尾（如 `$wolf-primary-v2`）
- ✅ 保留旧变量别名（如 `$wolf-primary: $wolf-primary-v2`）- 向后兼容
- ✅ 禁止硬编码（Stylelint 强制检查）

---

#### 0.2 创建基础组件库（第2周）

**必须先做的 5 个基础组件**（按优先级排序）：

| 组件 | 优先级 | 原因 | 工作量 | 必须包含 |
|------|--------|------|--------|---------|
| **ButtonV2** | P0 | 所有页面都用，影响范围最大 | 1天 | ✅ 3种状态（default/primary/danger）<br>✅ 2种尺寸（sm/md）<br>✅ 统一圆角 6px |
| **InputV2** | P0 | 所有表单都用 | 1天 | ✅ Focus 状态可见（2px outline）<br>✅ Error 状态明确<br>✅ 统一圆角 6px |
| **TableV2** | P0 | 所有列表页都用 | 2天 | ✅ 无竖分割线<br>✅ 自适应行高<br>✅ Hover 状态明显 |
| **CardV2** | P1 | 详情页都用 | 1天 | ✅ 统一阴影<br>✅ 统一圆角 6px<br>✅ Hover 状态 |
| **TabV2** | P1 | 详情页二级导航 | 1天 | ✅ Active 指示条设计<br>✅ 统一过渡动画 150ms |

**关键原则**：
- ✅ 每个组件必须有 `.stories.ts`（Storybook展示）
- ✅ 每个组件必须有 `.spec.ts`（单元测试）
- ✅ 每个组件必须引用 `MASTER.md` 的设计规则

---

#### 0.3 创建导航组件库（第3周）

**基于 navigation-redesign-v3.html 创建**：

| 组件 | 优先级 | 说明 | 工作量 |
|------|--------|------|--------|
| **SidebarV2** | P0 | 左侧全局菜单（含左侧指示条设计） | 2天 |
| **TopBarV2** | P0 | 顶部栏（含面包屑、操作按钮、审批铃铛） | 2天 |
| **ContextTabsV2** | P1 | 上下文标签栏（动态二级导航） | 2天 |
| **UserInfoDropdownV2** | P1 | 用户下拉菜单（含团队切换） | 1天 |

---

### **Phase 1: 渐进式迁移（4-6周）**

**只有在 Phase 0 完成后才开始**：

#### 1.1 试点页面（第1周）

**选择最简单的页面作为试点**：

| 页面 | 原因 | 工作量 | 输出 |
|------|------|--------|------|
| **线索管理（Leads.vue）** | 简单列表页，高频使用，适合试点 | 2天 | 试点验证新组件 |

**试点目标**：
- ✅ 验证新基础组件是否好用（ButtonV2、TableV2）
- ✅ 验证新导航组件是否好用（SidebarV2、TopBarV2）
- ✅ 验证新设计系统是否好用（variables-v2.scss）
- ✅ 发现问题并修复（避免后续大规模返工）

---

#### 1.2 核心页面迁移（第2-3周）

**迁移高频使用的核心页面**：

| 页面 | 优先级 | 工作量 | 迁移顺序 |
|------|--------|--------|---------|
| **客户管理（Customers.vue）** | P0 | 3天 | 1. 使用 SidebarV2 + TopBarV2<br>2. 使用 TableV2<br>3. 使用 ButtonV2 |
| **合同管理（Contracts.vue）** | P0 | 3天 | 同上 |
| **回款管理（Payments.vue）** | P0 | 2天 | 同上 |

---

#### 1.3 详情页迁移（第4-5周）

**迁移复杂页面**：

| 页面 | 优先级 | 工作量 | 特点 |
|------|--------|--------|------|
| **客户详情（CustomerDetail.vue）** | P1 | 5天 | 包含 ContextTabsV2、多个子组件 |
| **合同详情（ContractDetail.vue）** | P1 | 3天 | 包含 ContextTabsV2 |
| **审批中心（ApprovalCenter.vue）** | P2 | 2天 | 包含 ApprovalIcon优化版 |

---

### **Phase 2: 清理与优化（1-2周）**

**删除旧组件，统一标准**：

| 任务 | 工作量 | 说明 |
|------|--------|------|
| **删除旧变量** | 1天 | 移除 variables.scss 的旧变量别名 |
| **删除旧组件** | 2天 | 删除旧的 Button、Table、Sidebar 等 |
| **更新文档** | 1天 | 更新所有组件文档，引用 MASTER.md |

---

## ✅ 为什么必须先建立基础组件库？

### **风险对比分析**

| 风险类型 | 策略 A（基础先行） | 策略 B（直接迁移） |
|---------|------------------|------------------|
| **组件质量不稳定** | ✅ 低风险（先测试充分） | ❌ 高风险（边迁移边返工） |
| **样式不统一** | ✅ 低风险（统一 Tokens） | ❌ 高风险（可能重复定义） |
| **大规模返工** | ✅ 低风险（试点验证） | ❌ 高风险（发现问题需重做） |
| **团队协作混乱** | ✅ 低风险（统一标准） | ❌ 高风险（没有统一标准） |
| **向后兼容问题** | ✅ 低风险（别名保留） | ❌ 高风险（直接替换） |

---

## 📋 Phase 0 检查清单（必须完成后才能迁移）

完成以下清单后，才能进入 Phase 1：

### **Design Tokens 检查**

- ✅ `variables-v2.scss` 已创建
- ✅ 所有颜色变量已定义（primary、secondary、accent、success、warning、danger）
- ✅ 所有圆角变量已定义（统一 6px）
- ✅ 所有间距变量已定义（保留 8dp grid）
- ✅ 所有阴影变量已定义（中等强度）
- ✅ 向后兼容别名已添加（`$wolf-primary: $wolf-primary-v2`）
- ✅ `element-plus-theme-v2.scss` 已适配
- ✅ `MASTER.md` 已生成（UI/UX Pro Max）

### **基础组件检查**

- ✅ **ButtonV2** 已创建 + Storybook展示 + 单元测试
- ✅ **InputV2** 已创建 + Storybook展示 + 单元测试
- ✅ **TableV2** 已创建 + Storybook展示 + 单元测试
- ✅ **CardV2** 已创建 + Storybook展示 + 单元测试
- ✅ **TabV2** 已创建 + Storybook展示 + 单元测试

### **导航组件检查**

- ✅ **SidebarV2** 已创建 + Storybook展示 + 单元测试
- ✅ **TopBarV2** 已创建 + Storybook展示 + 单元测试
- ✅ **ContextTabsV2** 已创建 + Storybook展示 + 单元测试
- ✅ **UserInfoDropdownV2** 已创建 + Storybook展示 + 单元测试

### **强制规则检查**

- ✅ ESLint 配置已添加（禁止旧变量）
- ✅ Stylelint 配置已添加（禁止硬编码）
- ✅ Storybook 配置已添加（自动文档）

---

## 🎯 立即行动计划

### **第 1 周：建立 Design Tokens**

#### Day 1-2：创建 `variables-v2.scss`

```bash
# 文件：CRM-Client/src/styles/variables-v2.scss

# 1. 颜色系统（基于 navigation-redesign-v3.html）
$wolf-primary-v2: #2563EB;          # 主色
$wolf-secondary-v2: #3B82F6;        # 次色
$wolf-accent-v2: #059669;           # 强调色（成交绿）
$wolf-success-v2: #10B981;          # 成功色
$wolf-warning-v2: #F59E0B;          # 警告色
$wolf-danger-v2: #DC2626;           # 危险色

# 2. 圆角系统（统一 6px）
$wolf-radius-v2: 6px;               # 主圆角
$wolf-radius-sm-v2: 4px;            # 小圆角
$wolf-radius-lg-v2: 8px;            # 大圆角

# 3. 间距系统（保留 8dp grid）
$wolf-space-xs-v2: 4px;
$wolf-space-sm-v2: 8px;
$wolf-space-md-v2: 12px;
$wolf-space-lg-v2: 16px;

# 4. 阴影系统（中等强度）
$wolf-shadow-card-v2: 0 1px 3px rgba(0, 0, 0, 0.1);
$wolf-shadow-hover-v2: 0 2px 8px rgba(0, 0, 0, 0.15);

# 5. 向后兼容别名
$wolf-primary: $wolf-primary-v2;
```

#### Day 3：生成 `MASTER.md`

```bash
python3 skills/ui-ux-pro-max/scripts/search.py \
  "CRM enterprise dashboard navigation minimal professional" \
  --design-system --persist \
  -p "CRMWolf" \
  -f markdown
```

#### Day 4：适配 Element Plus 主题

```bash
# 文件：CRM-Client/src/styles/element-plus-theme-v2.scss

# 覆盖 Element Plus 默认主题
$--color-primary: $wolf-primary-v2;  # 使用新主色
$--border-radius-base: $wolf-radius-v2;  # 使用新圆角
```

---

### **第 2 周：创建基础组件库**

#### Day 1：创建 ButtonV2

**文件位置**：`CRM-Client/src/components/common/ButtonV2.vue`

```vue
<template>
  <button 
    class="button-v2"
    :class="[
      `button-v2--${variant}`,
      `button-v2--${size}`,
      { 'button-v2--disabled': disabled }
    ]"
    :disabled="disabled"
  >
    <slot />
  </button>
</template>

<script setup lang="ts">
defineProps<{
  variant: 'default' | 'primary' | 'danger'  // 3种状态
  size: 'sm' | 'md'                           // 2种尺寸
  disabled?: boolean
}>()
</script>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.button-v2 {
  border-radius: $wolf-radius-v2;  // ✅ 统一圆角 6px
  transition: $wolf-transition-v2;  // ✅ 统一过渡 150ms
  cursor: pointer;  // ✅ UX规则：cursor-pointer
  
  &:hover {
    // Hover 状态
  }
  
  &:active {
    // Active 状态
  }
  
  &:disabled {
    opacity: 0.5;  // ✅ UX规则：disabled state
    cursor: not-allowed;
  }
}

.button-v2--primary {
  background: $wolf-primary-v2;  // ✅ 使用新主色
  color: white;
}

.button-v2--danger {
  background: $wolf-danger-v2;
}
</style>
```

#### Day 2：创建 InputV2、TableV2

（参考 ButtonV2 模式，统一使用 `variables-v2.scss`）

#### Day 3：创建 Storybook 展示

**每个组件必须创建 `.stories.ts`**：

```typescript
// ButtonV2.stories.ts
import type { Meta, StoryObj } from '@storybook/vue3'
import ButtonV2 from './ButtonV2.vue'

const meta: Meta<typeof ButtonV2> = {
  title: 'Common/ButtonV2',
  component: ButtonV2,
  tags: ['autodocs'],
  parameters: {
    docs: {
      description: {
        component: '引用规则：design-system/crmwolf/MASTER.md'
      }
    }
  }
}

export default meta
export const Primary: Story = {
  args: { variant: 'primary', size: 'md' }
}

export const Danger: Story = {
  args: { variant: 'danger', size: 'md' }
}
```

---

## 📊 时间预估

| 阶段 | 工作内容 | 时间 | 里程碑 |
|------|---------|------|--------|
| **Phase 0** | Design Tokens + 基础组件库 | 2-3周 | ✅ 所有基础组件就绪 |
| **Phase 1** | 试点页面 + 核心页面迁移 | 4-6周 | ✅ 所有核心页面使用新设计 |
| **Phase 2** | 清理旧组件 + 优化 | 1-2周 | ✅ 100% 使用新设计系统 |
| **总计** | 完整迁移 | **7-11周** | ✅ 整体替换、统一标准、组件化 |

---

## 💡 核心建议

**记住**：**基础先行，渐进迁移**。这是降低风险、保证质量的关键。

### **三个必须遵守的原则**

| 原则 | 说明 | 违反后果 |
|------|------|---------|
| **1. Phase 0 必须完成** | Design Tokens + 基础组件库必须先就绪 | ❌ 直接迁移会导致大规模返工 |
| **2. 试点验证** | 先迁移一个简单页面，验证新组件 | ❌ 跳过试点会导致后续批量问题 |
| **3. 强制规则** | ESLint + Stylelint 强制使用新标准 | ❌ 没有强制规则会导致样式不统一 |

---

## 🎯 立即开始

**第一步**：创建 `variables-v2.scss`（参考上面的代码）

**完成标志**：Phase 0 检查清单全部 ✅ 后，才能进入 Phase 1

---

**总结**：先建立基础组件库（Design Tokens + ButtonV2 + TableV2 + 导航组件），再迁移页面。这是确保"整体替换、统一标准、组件化"三个核心目标的唯一正确顺序。