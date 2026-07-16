---
priority: high
status: active
---

# CRMWolf 布局与层级管理规范

**适用范围**：CRM-Client 全项目

**权威说明**：本文档是 z-index 层级和布局架构的单一事实来源，所有组件必须遵循此规范。

---

## 一、z-index 层级管理

### 1.1 层级定义（基于 UI/UX Pro Max §5）

所有组件必须遵循以下层级系统，禁止使用任意 z-index 值：

| 层级 | z-index | 用途 | 示例组件 | 来源 |
|------|---------|------|---------|------|
| **1000** | `z-[1000]` | Modal 层 | Dialog, Dropdown, AlertDialog | AppLayout `$z-index-modal` |
| **200** | `z-[200]` | Drawer 层 | Sheet, Drawer | 介于 TopBar 与 Modal |
| **100** | `z-100` | 主导航 | Sidebar, BottomNav | AppLayout `$z-index-sidebar` |
| **90** | `z-90` | 固定导航栏 | TopBar (sticky header) | AppLayout `$z-index-topbar` |
| **50** | `z-50` | 临时通知 | Toast, Notifications | UI/UX Pro Max §5 |
| **20** | `z-20` | 悬浮元素 | Tooltip, Popover, ContextMenu | UI/UX Pro Max §5 |
| **10** | `z-10` | 基础内容 | 页面内容、卡片 | UI/UX Pro Max §5 |

### 1.2 Portal 组件层级规则

**强制要求**：所有 Modal/Drawer 组件必须通过 Portal 渲染到 `<body>`，避免 CSS stacking context 冲突。

| 组件类型 | z-index | Portal | 原因 |
|---------|---------|--------|------|
| **Dialog** | `z-[1000]` | ✅ 必须 | 最高层级，遮挡一切 |
| **AlertDialog** | `z-[1000]` | ✅ 必须 | 与 Dialog 同层，确认对话框 |
| **DropdownMenu** | `z-[1000]` | ✅ 必须 | 下拉菜单，与 Modal 同层 |
| **ContextMenu** | `z-[1000]` | ✅ 必须 | 右键菜单，与 Modal 同层 |
| **Select** | `z-[1000]` | ✅ 必须 | 下拉选择框，与 Modal 同层 |
| **Combobox** | `z-[1000]` | ✅ 必须 | 组合框，与 Modal 同层 |
| **Popover** | `z-[1000]` | ✅ 必须 | 弹出框，与 Modal 同层 |
| **Menubar** | `z-[1000]` | ✅ 必须 | 菜单栏，与 Modal 同层 |
| **Sheet** | `z-[200]` | ✅ 必须 | Drawer 层，遮挡导航但不遮挡 Modal |
| **Drawer** | `z-[200]` | ✅ 必须 | 与 Sheet 同层 |
| **Tooltip** | `z-20` | ✅ 推荐 | 悬浮提示，依附于触发元素 |
| **HoverCard** | `z-20` | ✅ 推荐 | 悬浮卡片，依附于触发元素 |

### 1.3 层级关系图

```
┌─────────────────────────────────────────────────┐
│ z-1000: Dialog Overlay + Content (Modal)       │ ← 最高层级（$z-index-modal）
│ z-1000: Dropdown (用户下拉菜单)                 │ ← 与 Modal 同层
├─────────────────────────────────────────────────┤
│ z-200:  Sheet Overlay + Content (Drawer)       │ ← Drawer 层
├─────────────────────────────────────────────────┤
│ z-100:  Sidebar, BottomNav                     │ ← 主导航
│ z-90:   TopBar (sticky header)                 │ ← 固定导航栏
├─────────────────────────────────────────────────┤
│ z-50:   Toast, Notifications                   │ ← 临时通知
│ z-20:   Tooltip, Popover                       │ ← 悬浮元素
│ z-10:   基础内容                                │ ← 页面主体
└─────────────────────────────────────────────────┘
```

**层级关系公式**：

```
Dialog (z-1000) > Sheet (z-200) > TopBar (z-90) > Sidebar (z-100)
Modal > Drawer > Navigation > Content
```

---

## 二、组件实现规范

### 2.1 Dialog 组件（Modal 层）

**来源**：`src/components/ui/dialog/DialogContent.vue`

**强制配置**：

```vue
<!-- DialogContent.vue -->
<template>
  <DialogPortal>
    <!-- Overlay: z-[1000] -->
    <DialogOverlay
      class="fixed inset-0 z-[1000] bg-black/80 ..."
    />
    <!-- Content: z-[1000] -->
    <DialogContent
      :class="cn('fixed left-1/2 top-1/2 z-[1000] ...', props.class)"
    >
      <slot />
    </DialogContent>
  </DialogPortal>
</template>
```

**禁止行为**：

| 禁止 | 原因 |
|------|------|
| ❌ `z-50` | 低于 Sheet (z-200)，无法遮挡 Sheet |
| ❌ `z-[9999]` | 违反 UI/UX Pro Max §5 "no arbitrary values" |
| ❌ 不使用 Portal | CSS stacking context 冲突 |

### 2.2 Sheet 组件（Drawer 层）

**来源**：`src/components/ui/sheet/SheetContent.vue` + `index.ts`

**强制配置**：

```vue
<!-- SheetContent.vue -->
<template>
  <DialogPortal>
    <!-- Overlay: z-[200] -->
    <DialogOverlay
      class="fixed inset-0 z-[200] bg-black/80 ..."
    />
    <!-- Content: z-[200] -->
    <DialogContent
      :class="cn('fixed z-[200] ...', props.class)"
    >
      <slot />
    </DialogContent>
  </DialogPortal>
</template>
```

```typescript
// sheet/index.ts
export const sheetVariants = cva(
  "fixed z-[200] gap-4 bg-background p-6 shadow-lg ...",
  { ... }
)
```

**禁止行为**：

| 禁止 | 原因 |
|------|------|
| ❌ `z-[1000]` | 与 Dialog 同层，导致层级冲突 |
| ❌ `z-40` 或更低 | 低于 TopBar (z-90)，被导航遮挡 |
| ❌ 不使用 Portal | CSS stacking context 冲突 |

### 2.3 TopBar 组件（固定导航栏）

**来源**：`src/AppLayout.vue`

**强制配置**：

```scss
// AppLayout.vue
.top-bar {
  position: sticky;
  top: 0;
  z-index: $z-index-topbar;  // 90（必须在 Sheet z-200 之下）
  height: $wolf-topbar-height-v2;  // 56px
  ...
}
```

**设计意图**：

- TopBar 是 **sticky header**，固定在页面顶部
- z-index: 90，低于 Sheet (z-200)，允许 Sheet 遮挡 TopBar
- 符合 Material Design Drawer 规范

---

## 三、常见场景与解决方案

### 3.1 Sheet 内打开 Dialog（Modal on Drawer）

**场景**：LeadDetailSheet 内点击"添加跟进"按钮，打开 FollowUpDialog

**正确实现**：

```vue
<!-- LeadDetailSheet.vue -->
<template>
  <!-- Sheet: z-200 -->
  <Sheet :open="visible">
    <SheetContent>
      <!-- Dialog trigger -->
      <Button @click="showFollowUpDialog = true">添加跟进</Button>
    </SheetContent>
  </Sheet>

  <!-- Dialog: z-1000（在 Sheet 外部） -->
  <Dialog v-model:open="showFollowUpDialog">
    <DialogContent>
      <!-- Dialog 内容 -->
    </DialogContent>
  </Dialog>
</template>
```

**层级关系**：

```
Dialog (z-1000) > Sheet Overlay (z-200) > Sheet Content (z-200) > TopBar (z-90)
```

**关键点**：

- Dialog 必须渲染在 Sheet **外部**（同级，不在 Sheet 内）
- Portal 自动将 Dialog 渲染到 `<body>`，避免层级问题
- Dialog 的 z-index (1000) > Sheet 的 z-index (200)

### 3.2 Dropdown 在 Sheet 内

**场景**：Sheet 内的用户下拉菜单

**正确实现**：

```vue
<!-- AppLayout.vue -->
<template>
  <!-- Sheet: z-200 -->
  <Sheet>
    <SheetContent>
      <!-- Dropdown: z-1000（通过 Portal） -->
      <DropdownMenu>
        <DropdownMenuTrigger>切换团队</DropdownMenuTrigger>
        <DropdownMenuContent>  <!-- Portal 渲染，z-1000 -->
          <DropdownMenuItem>团队 A</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </SheetContent>
  </Sheet>
</template>
```

**层级关系**：

```
Dropdown (z-1000) > Sheet (z-200)
```

### 3.3 Toast 显示在 Sheet 上方

**场景**：Sheet 内提交表单，显示 Toast 提示

**正确实现**：

```vue
<!-- 使用 vue-sonner -->
<script setup>
import { toast } from 'vue-sonner'

const handleSubmit = async () => {
  await api.submit()
  toast.success('提交成功')  // Toast 自动 z-50 或更高
}
</script>
```

**注意**：

- vue-sonner 的 Toast 通常使用 `z-[9999]` 或更高
- 如果 Toast z-index 过低，需要调整 Toast 库配置
- 确保 Toast > Sheet (z-200)

---

## 四、调试与验证

### 4.1 z-index 检查清单

**每个 Modal/Drawer 组件上线前必须验证**：

| 检查项 | 验证方法 | 通过标准 |
|--------|---------|---------|
| ✅ Portal 渲染 | DevTools → Elements → body 子元素 | Dialog/Sheet 在 `<body>` 内 |
| ✅ z-index 值 | DevTools → Styles → z-index | Dialog: z-[1000], Sheet: z-[200] |
| ✅ 层级关系 | 打开 Sheet → 打开 Dialog | Dialog 显示在 Sheet 上方 |
| ✅ 导航遮挡 | 打开 Sheet | Sheet 遮挡 TopBar/Sidebar |

### 4.2 常见问题排查

#### 问题 1：Dialog 显示在 Sheet 下面

**根本原因**：Dialog z-index < Sheet z-index

**排查步骤**：

```bash
# 1. 检查 Dialog z-index
grep -n "z-\[" src/components/ui/dialog/DialogContent.vue

# 2. 检查 Sheet z-index
grep -n "z-\[" src/components/ui/sheet/index.ts

# 3. 验证层级关系
# Dialog (z-1000) > Sheet (z-200)
```

**修复方案**：

- Dialog: `z-[1000]`
- Sheet: `z-[200]`

#### 问题 2：Sheet 被 TopBar 遮挡

**根本原因**：Sheet z-index < TopBar z-index

**排查步骤**：

```bash
# 1. 检查 Sheet z-index
grep -n "z-\[" src/components/ui/sheet/SheetContent.vue

# 2. 检查 TopBar z-index
grep -n "z-index-topbar" src/AppLayout.vue

# 3. 验证层级关系
# Sheet (z-200) > TopBar (z-90)
```

**修复方案**：

- Sheet: `z-[200]`（必须 > TopBar z-90）

#### 问题 3：CSS Stacking Context 冲突

**根本原因**：Modal 未使用 Portal，被父组件 z-index 影响

**排查方法**：

```bash
# DevTools → Elements → 检查 Modal DOM 位置
# 如果 Modal 在 SheetContent 内 → Stacking Context 冲突
```

**修复方案**：

- 所有 Modal 必须使用 Portal（DialogPortal/DialogPortal）
- shadcn-vue/reka-ui 已自动使用 Portal，无需额外配置

---

## 五、设计依据

### 5.1 参考规范

| 规范 | 章节 | 关键规则 |
|------|------|---------|
| **UI/UX Pro Max** | §5: z-index-management | Define z-index scale system (10 20 30 50) |
| **UI/UX Pro Max** | §5: stacking-context | Understand what creates new stacking context |
| **Material Design** | Navigation Drawer | Drawer z-index > App Bar |
| **Apple HIG** | Modals | Modal is highest layer |

### 5.2 shadcn-vue/reka-ui 架构

shadcn-vue 基于 reka-ui 实现，自动使用 Portal：

- **DialogPortal**：将 Modal 渲染到 `<body>`
- **DialogContent**：z-index 配置在组件内部
- **DialogOverlay**：Scrim (遮罩层) z-index 配置

**关键源文件**：

- `src/components/ui/dialog/DialogContent.vue`
- `src/components/ui/sheet/SheetContent.vue`
- `src/components/ui/sheet/index.ts`
- `src/AppLayout.vue`（z-index 变量定义）

---

## 六、变更记录

| 日期 | 变更内容 | 原因 |
|------|---------|------|
| 2026-07-10 | 创建文档 | 解决 Sheet/Dialog z-index 冲突问题 |
| 2026-07-10 | 定义层级系统 | 统一 z-index 管理，避免未来冲突 |

---

**维护说明**：

- 本文档是 **z-index 层级的单一事实来源**
- 所有新 Modal/Drawer 组件必须遵循此规范
- 修改 z-index 值需要同步更新此文档
- 参考 `src/AppLayout.vue` 的 `$z-index-*` 变量定义