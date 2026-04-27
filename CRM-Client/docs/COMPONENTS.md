# Vue 组件开发规范 - CRMWolf

**适用范围**：CRM-Client/src/components 和 views

---

## 一、组件模板（强制结构）

```vue
<script setup lang="ts">
// ===== 1. 导入区（按字母排序） =====
import { computed, onMounted, ref } from 'vue'
import type { PropType } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'

// ===== 2. 类型导入（从 Approved Types） =====
import type { CustomerResponse, CustomerCreate } from '@/schemas/customer'

// ===== 3. Props 定义（必须类型化） =====
const props = defineProps({
  customer: {
    type: Object as PropType<CustomerResponse>,
    required: true
  },
  mode: {
    type: String as PropType<'view' | 'edit'>,
    default: 'view'
  }
})

// ===== 4. Emits 定义（必须类型化） =====
const emit = defineEmits<{
  (e: 'update', value: CustomerCreate): void
  (e: 'delete', id: number): void
  (e: 'close'): void
}>()

// ===== 5. Store 使用 =====
const userStore = useUserStore()

// ===== 6. 本地状态（必须类型化） =====
const loading = ref<boolean>(false)
const formData = ref<CustomerCreate>({
  account_name: '',
  city: ''
})

// ===== 7. 计算属性（必须返回类型） =====
const displayName = computed<string>(() => {
  return props.customer.account_name || '未命名'
})

const canEdit = computed<boolean>(() => {
  return userStore.permissions.includes('customer:update')
})

// ===== 8. 方法（必须参数和返回类型） =====
const handleSave = async (): Promise<void> => {
  loading.value = true
  try {
    emit('update', formData.value)
  } finally {
    loading.value = false
  }
}

const handleDelete = (): void => {
  emit('delete', props.customer.id)
}

// ===== 9. 生命周期 =====
onMounted(() => {
  formData.value = { ...props.customer }
})
</script>

<template>
  <div class="customer-card">
    <!-- 使用 wolf-design 样式类 -->
    <h3 class="wolf-title">{{ displayName }}</h3>

    <!-- 条件渲染 -->
    <div v-if="loading" class="wolf-loading">
      加载中...
    </div>

    <!-- 权限控制 -->
    <button
      v-if="canEdit"
      class="wolf-btn-primary"
      @click="handleSave"
    >
      保存
    </button>
  </div>
</template>

<style scoped>
/* 使用 styles/variables.scss 设计变量 */
.customer-card {
  padding: var(--wolf-spacing-md);
}
</style>
```

---

## 二、Props 规范

| 规则 | 要求 |
|------|------|
| 类型声明 | 必须使用 `Object as PropType<T>` |
| required/default | 必须明确指定 |
| 禁止 any | Props 禁止使用 any 类型 |

### 2.1 对象 Props

```typescript
// 正确
const props = defineProps({
  customer: {
    type: Object as PropType<CustomerResponse>,
    required: true
  }
})

// 禁止
const props = defineProps({
  customer: Object  // 无类型
})
```

### 2.2 数组 Props

```typescript
// 正确
const props = defineProps({
  items: {
    type: Array as PropType<CustomerResponse[]>,
    default: () => []
  }
})
```

### 2.3 枚举 Props

```typescript
// 正确
const props = defineProps({
  status: {
    type: String as PropType<'0' | '1' | '2' | '3'>,
    default: '0'
  }
})
```

---

## 三、Emits 规范

| 规则 | 要求 |
|------|------|
| 类型声明 | 必须使用泛型 `<{ ... }>` |
| 参数类型 | 每个 emit 必须声明参数类型 |

```typescript
// 正确
const emit = defineEmits<{
  (e: 'update', value: CustomerCreate): void
  (e: 'change', id: number, status: CustomerStatus): void
}>()

// 禁止
const emit = defineEmits(['update', 'delete'])  // 无类型
```

---

## 四、组件分类

### 4.1 共享组件（components/）

| 要求 | 说明 |
|------|------|
| Stories 文件 | 必须创建 `.stories.ts` |
| Props 文档 | 必须在 Stories 中展示所有 props |
| 可复用 | 不依赖特定业务上下文 |

### 4.2 页面组件（views/）

| 要求 | 说明 |
|------|------|
| 类型导入 | 从 schemas/ 导入，禁止内联定义 |
| API 调用 | 可直接调用 api/ |
| 状态管理 | 可使用 stores/ |

---

## 五、Storybook 要求

每个共享组件必须创建 Stories 文件：

```typescript
// components/CustomerCard.stories.ts
import type { Meta, StoryObj } from '@storybook/vue3'
import CustomerCard from './CustomerCard.vue'
import type { CustomerResponse } from '@/schemas/customer'

const meta: Meta<typeof CustomerCard> = {
  title: 'Customer/CustomerCard',
  component: CustomerCard
}

export default meta
type Story = StoryObj<typeof CustomerCard>

const mockCustomer: CustomerResponse = {
  id: 1,
  account_name: '测试公司',
  city: '北京',
  status: '0',
  creator_id: 'test',
  created_time: '2024-01-01',
  last_modified_time: '2024-01-01',
  version: 1
}

export const Default: Story = {
  args: {
    customer: mockCustomer
  }
}

export const EditMode: Story = {
  args: {
    customer: mockCustomer,
    mode: 'edit'
  }
}
```

---

## 六、样式规范

| 规则 | 要求 |
|------|------|
| CSS 变量 | 使用 styles/variables.scss 定义的变量 |
| scoped | 所有组件样式必须 scoped |
| 禁止内联 | 复杂样式禁止写在 style 属性 |

```css
/* 正确 - 使用设计变量 */
.card {
  padding: var(--wolf-spacing-md);
  color: var(--wolf-text-primary);
}

/* 禁止 - 硬编码 */
.card {
  padding: 16px;
  color: #333;
}
```

---

## 七、禁止行为

| 禁止 | 原因 |
|------|------|
| Props 使用 any | 违反类型安全 |
| 内联定义类型 | 违反单一来源 |
| 组件直接调用 API | 违反分层 |
| 禁止 Stories | 违反测试要求 |

---

## 八、校验规则

| 校验点 | 工具 | 时机 |
|--------|------|------|
| Props 类型 | ESLint `require-prop-types` | pre-commit |
| Stories 存在 | Git hooks 文件检测 | pre-commit |
| 样式 scoped | ESLint Vue 规则 | pre-commit |

---

**版本：1.0 | 最后更新：2026-04-21 | 修改需人工审批**