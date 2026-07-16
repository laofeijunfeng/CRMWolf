# Task 6: 创建 ErrorMessage 组件（如不存在）

**Files:**
- Create: `CRM-Client/src/components/ui/form/ErrorMessage.vue`
- Modify: `CRM-Client/src/components/ui/form/index.ts`

**Interfaces:**
- Consumes: `role="alert"` 属性用于屏幕阅读器通知
- Produces: 带有 aria-live 支持的错误消息组件

## UI/UX Pro Max 要求

- 使用 `role="alert"` 实现自动 aria-live
- 错误消息必须可被屏幕阅读器感知

## Implementation

- [ ] **Step 1: 检查 ErrorMessage 组件是否存在**

Run: `ls CRM-Client/src/components/ui/form/`
Expected: 如果没有 ErrorMessage.vue 则创建

- [ ] **Step 2: 创建 ErrorMessage 组件（如不存在）**

```vue
<!-- CRM-Client/src/components/ui/form/ErrorMessage.vue -->
<script setup lang="ts">
import { cn } from '@/lib/utils'

interface Props {
  message?: string
  class?: string
}

const props = withDefaults(defineProps<Props>(), {
  message: undefined,
  class: undefined,
})
</script>

<template>
  <p
    v-if="message"
    role="alert"
    :class="cn('text-sm font-medium text-destructive', props.class)"
    aria-live="polite"
  >
    {{ message }}
  </p>
</template>
```

- [ ] **Step 3: 导出 ErrorMessage（更新 index.ts）**

在 `CRM-Client/src/components/ui/form/index.ts` 中添加导出：
```typescript
export { default as ErrorMessage } from './ErrorMessage.vue'
```

- [ ] **Step 4: 运行类型检查**

Run: `cd CRM-Client && npm run type-check`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add CRM-Client/src/components/ui/form/ErrorMessage.vue
git add CRM-Client/src/components/ui/form/index.ts
git commit -m "feat(form): add ErrorMessage component with aria-live support for accessibility"
```