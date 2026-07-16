# DetailSheet 组件统一封装

**创建日期**：2026-07-13

**目的**：统一管理所有详情页 Sheet 的样式和 z-index，避免层级冲突。

---

## 一、问题背景

### 1.1 原始问题

**OpportunityDetailSheet 显示在遮罩层下面**：

```vue
<!-- OpportunityDetailSheet.vue (修改前) -->
<SheetContent
  style="z-index: 100"  <!-- ❌ 硬编码错误值 -->
>
```

**问题分析**：
- Sheet Overlay: `z-[200]`
- SheetContent 应该是: `z-[201]`（在 Overlay 之上）
- 但硬编码 `z-index: 100` < Overlay 的 `z-[200]`
- 导致内容显示在遮罩下面

### 1.2 设计规范依据

| 文档 | 章节 | 关键规则 |
|------|------|---------|
| **docs/LAYOUT.md** | §1.2 | SheetContent z-[201] > Overlay z-[200] |
| **MASTER.md** | §3.5 | 组件封装原则：仅封装样式，保留原生动态效果 |

---

## 二、解决方案

### 2.1 创建 DetailSheetContent 组件

**路径**：`src/components/ui/detail-sheet/DetailSheetContent.vue`

**核心代码**：

```vue
<script setup lang="ts">
/**
 * DetailSheetContent - 统一的详情页 Sheet 组件
 *
 * 基于 MASTER.md §6.6 布局架构和 LAYOUT.md z-index 管理：
 * - 宽度：w-2/3 max-w-[880px]（右侧 2/3）
 * - z-index：使用 SheetContent 默认 z-[201]（高于 Overlay z-[200]）
 * - 样式：统一白色背景、无边距（p-0）
 */
import { SheetContent } from '@/components/ui/sheet'
</script>

<template>
  <SheetContent
    side="right"
    class="w-2/3 max-w-[880px] sm:max-w-[880px] p-0 flex flex-col bg-white dark:bg-slate-900"
  >
    <slot />
  </SheetContent>
</template>
```

### 2.2 组件特性

| 特性 | 值 | 说明 |
|------|-----|------|
| **宽度** | `w-2/3 max-w-[880px]` | 右侧 2/3，最大 880px |
| **z-index** | `z-[201]`（默认） | 高于 Overlay z-[200]，低于 Dialog z-[1000] |
| **背景色** | `bg-white dark:bg-slate-900` | 支持暗色模式 |
| **内边距** | `p-0` | 无内边距，由内部组件控制 |

### 2.3 遵循 MASTER.md §3.5 组件封装原则

| 原则 | 实现 |
|------|------|
| ✅ 仅封装样式 | 只设置宽度、背景色、内边距 |
| ✅ 保留原生动态效果 | 使用 SheetContent 默认动画和过渡 |
| ✅ z-index 层级正确 | 不硬编码，使用 SheetContent 默认值 |

---

## 三、迁移清单

### 3.1 已迁移组件

| 组件 | 路径 | 迁移日期 | 状态 |
|------|------|---------|------|
| **LeadDetailSheet** | `src/views/LeadDetailSheet.vue` | 2026-07-13 | ✅ 已迁移 |
| **OpportunityDetailSheet** | `src/views/OpportunityDetailSheet.vue` | 2026-07-13 | ✅ 已迁移（修复 z-index 问题） |
| **CustomerDetailSheet** | `src/views/CustomerDetailSheet.vue` | 2026-07-13 | ✅ 已迁移 |

### 3.2 迁移示例

**迁移前**：

```vue
<template>
  <Sheet :open="visible">
    <SheetContent
      side="right"
      class="w-2/3 max-w-[880px] sm:max-w-[880px] p-0 flex flex-col bg-white dark:bg-slate-900"
      style="z-index: 100"  <!-- ❌ 硬编码 -->
    >
      <!-- 内容 -->
    </SheetContent>
  </Sheet>
</template>
```

**迁移后**：

```vue
<script setup>
import { DetailSheetContent } from '@/components/ui/detail-sheet'
</script>

<template>
  <Sheet :open="visible">
    <DetailSheetContent>
      <!-- 内容 -->
    </DetailSheetContent>
  </Sheet>
</template>
```

---

## 四、验证清单

### 4.1 功能验证

| 检查项 | 验证方法 | 状态 |
|--------|---------|------|
| ✅ Sheet 正常显示 | 打开详情页，检查 Sheet 可见 | 待测试 |
| ✅ z-index 层级正确 | Sheet 内容在遮罩上方 | 待测试 |
| ✅ 宽度统一 | 所有详情页 Sheet 宽度一致 | 待测试 |
| ✅ 暗色模式 | 切换暗色模式，背景色正确 | 待测试 |

### 4.2 TypeScript 检查

```bash
npm run type-check
```

**结果**：无新增类型错误（现有错误与本次修改无关）

---

## 五、维护说明

### 5.1 未来新增 DetailSheet

**步骤**：

1. 导入 `DetailSheetContent`：

   ```vue
   <script setup>
   import { DetailSheetContent } from '@/components/ui/detail-sheet'
   </script>
   ```

2. 使用组件：

   ```vue
   <template>
     <Sheet :open="visible">
       <DetailSheetContent>
         <!-- 内容 -->
       </DetailSheetContent>
     </Sheet>
   </template>
   ```

### 5.2 禁止事项

| 禁止 | 原因 |
|------|------|
| ❌ 硬编码 z-index | 破坏层级管理，导致显示问题 |
| ❌ 修改 SheetContent 默认样式 | 违反 MASTER.md §3.5 组件封装原则 |
| ❌ 在 DetailSheetContent 内添加额外样式 | 应该在内部组件中控制 |

---

## 六、设计依据

| 规范 | 章节 | 关键规则 |
|------|------|---------|
| **MASTER.md** | §3.5 | 组件封装原则：仅封装样式，保留原生动态效果 |
| **docs/LAYOUT.md** | §1.1 | z-index 层级系统：SheetContent z-[201] |
| **docs/LAYOUT.md** | §2.2 | Sheet 组件强制配置 |
| **UI/UX Pro Max** | §5 | z-index-management：Define z-index scale system |

---

**维护负责人**：前端团队

**文档版本**：V1.0 | **最后更新**：2026-07-13