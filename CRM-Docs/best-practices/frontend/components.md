# 组件开发规范

> 前端组件开发必须遵循此规范，确保组件可复用、可维护。

---

## 组件通信原则

### 🟢 推荐做法：Props + Events

```typescript
// 父组件
<ChildComponent
  :data="parentData"
  :disabled="isDisabled"
  @update="handleUpdate"
  @delete="handleDelete"
/>

// 子组件
const props = defineProps<{
  data: Customer
  disabled?: boolean
}>()

const emit = defineEmits<{
  update: [Customer]
  delete: [number]
}>()

// 触发事件
emit('update', newData)
emit('delete', id)
```

### 🔴 禁止做法

```typescript
// ❌ 禁止直接修改 props
props.data.name = 'new name'

// ❌ 禁止直接访问父组件
parent.someMethod()

// ❌ 禁止通过 ref 暴露内部方法（除非必要）
defineExpose({ internalMethod })  // 仅在特殊场景使用
```

---

## Props 定义规范

### 🟢 推荐做法

```typescript
// 使用 TypeScript 类型定义
interface Props {
  data: Customer          // 必填
  disabled?: boolean      // 可选
  mode?: 'edit' | 'view'  // 枚举
}

const props = defineProps<Props>()

// 或使用 withDefaults
const props = withDefaults(defineProps<Props>(), {
  disabled: false,
  mode: 'view'
})
```

### 🔴 禁止做法

```typescript
// ❌ 禁止使用运行时 props 定义
props: {
  data: Object,
  disabled: Boolean
}

// ❌ 禁止使用 any 类型
const props = defineProps<{ data: any }>()
```

---

## Events 定义规范

### 🟢 推荐做法

```typescript
// 使用类型化 emit
const emit = defineEmits<{
  update: [Customer]       // 带参数
  delete: [number]         // 带参数
  close: []                // 无参数
}>()

emit('update', newData)
emit('delete', id)
emit('close')
```

### 🔴 禁止做法

```typescript
// ❌ 禁止使用字符串 emit（无类型检查）
this.$emit('update', newData)

// ❌ 禁止 emit 空对象
emit('update', {} as Customer)
```

---

## 组件结构规范

### 🟢 推荐的组件结构

```vue
<template>
  <!-- 模板内容 -->
</template>

<script setup lang="ts">
// 1. Props/Emits 定义
interface Props { ... }
const props = defineProps<Props>()
const emit = defineEmits<{ ... }>()

// 2. 组件状态
const localState = ref()

// 3. 计算属性
const computedValue = computed(() => ...)

// 4. 方法
const handleAction = () => { ... }

// 5. 生命周期
onMounted(() => { ... })
</script>

<style scoped lang="scss">
// 样式内容
</style>
```

---

## 组件命名规范

| 类型 | 前缀 | 示例 |
|------|------|------|
| 页面组件 | 无 | `CustomerList.vue` |
| 业务组件 | 无 | `CustomerCard.vue` |
| 通用组件 | 无 | `Button.vue`、`Modal.vue` |
| 表单组件 | Form | `CustomerForm.vue` |
| 详情组件 | Detail | `CustomerDetail.vue` |
| 编辑组件 | Edit | `CustomerEdit.vue` |

---

## 组件复用原则

### 🟢 推荐做法

```typescript
// 通用组件：只接收 props，通过 emit 回调
<Button :loading="isLoading" @click="handleClick">
  提交
</Button>

// 业务组件：封装业务逻辑，只暴露必要接口
<CustomerSelector
  v-model="selectedCustomer"
  :exclude-ids="excludedIds"
/>
```

### 🔴 禁止做法

```typescript
// ❌ 禁止通用组件依赖特定业务数据
<Button :customer-id="customerId" />  // Button 不应知道 customer

// ❌ 禁止组件内部直接调用 API（除非是业务组件）
const handleClick = async () => {
  await request.post('/v1/customers/', data)  // 通用组件不应调用 API
}
```

---

## 组件划分原则

### 何时拆分组件？

| 场景 | 建议 |
|------|------|
| 代码超过 200 行 | 拆分子组件 |
| 有重复的 UI 结构 | 抽取通用组件 |
| 有独立的状态逻辑 | 拆分业务组件 |
| 单一职责原则 | 一个组件只做一件事 |

### 拆分示例

```typescript
// 拆分前：一个组件 300 行
<CustomerDetail>  <!-- 包含基本信息、跟进记录、合同列表 -->

// 拆分后：多个职责清晰的组件
<CustomerDetail>
  <CustomerBasicInfo :customer="customer" @update="handleUpdate" />
  <CustomerFollowUpList :customer-id="customer.id" />
  <CustomerContractList :customer-id="customer.id" />
</CustomerDetail>
```

---

## 相关文档

- [state-management.md](state-management.md) - 状态管理规范
- [forms.md](forms.md) - 表单处理规范