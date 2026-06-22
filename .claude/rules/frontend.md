# 前端开发规则

**适用范围**：CRM-Client/src 所有 .ts 和 .vue 文件

---

## TypeScript 四禁令（零妥协）

| 禁令 | 曝光后果 | 替代方案 |
|------|----------|----------|
| `: any` | 阻止提交 | 使用 TYPESCRIPT.md Approved Types |
| `as any` | 阻止提交 | 使用 Zod 校验 + Approved Types |
| `@ts-ignore` | 阻止提交 | 修复错误源，不隐藏 |
| `!` 非空断言 | 阻止提交 | 使用 `?.` 条件判断 |

### 替代示例

```typescript
// 禁止
const params: any = { page: 1 }
const response = await api.getCustomers() as any
// @ts-ignore
someUntypedFunction()
const id = customer.value!.id

// 正确
const params: PaginationParams = { page: 1, pageSize: 20 }
const response = CustomerListResponseSchema.parse(await api.getCustomers())
function someTypedFunction(): void { ... }
const id = customer.value?.id ?? 0
```

---

## Vue 组件规范

### Props 规范

| 规则 | 要求 |
|------|------|
| 类型声明 | 必须使用 `Object as PropType<T>` |
| required/default | 必须明确指定 |
| 禁止 any | Props 禁止使用 any 类型 |

```typescript
// 正确
const props = defineProps({
  customer: {
    type: Object as PropType<CustomerResponse>,
    required: true
  }
})

// 禁止
const props = defineProps({ customer: Object })  // 无类型
```

### Emits 规范

| 规则 | 要求 |
|------|------|
| 类型声明 | 必须使用泛型 `<{ ... }>` |
| 参数类型 | 每个 emit 必须声明参数类型 |

```typescript
// 正确
const emit = defineEmits<{
  (e: 'update', value: CustomerCreate): void
  (e: 'delete', id: number): void
}>()

// 禁止
const emit = defineEmits(['update', 'delete'])  // 无类型
```

### 类型来源

| 规则 | 要求 |
|------|------|
| 类型导入 | 从 `schemas/` 导入，禁止内联定义 |
| 后端同步 | 前端类型必须映射后端 Pydantic schema |

---

## Pinia Store 规范

### State 规范

| 规则 | 要求 |
|------|------|
| 类型声明 | 必须 `ref<Type>(...)` |
| 禁止 any | State 禁止使用 any 类型 |

```typescript
// 正确
const loading = ref<boolean>(false)
const items = ref<CustomerResponse[]>([])

// 禁止
const loading = ref(false)  // 无类型
const data = ref<any>(null)  // 使用 any
```

### 解构规则

```typescript
// 正确 - State/Computed 使用 storeToRefs
const { items, loading } = storeToRefs(store)

// 正确 - Actions 直接解构
const { fetchList, create } = store

// 禁止 - State 直接解构（失去响应性）
const { items } = store
```

---

## API 请求规范

| 规则 | 要求 |
|------|------|
| baseURL | 复用 `request.ts` 配置，禁止硬编码 |
| SSE 流式 | 使用 `/api/v1/xxx` 完整路径 |
| Zod 校验 | 所有 API 响应必须有 Zod schema 校验 |

---

## Storybook 要求

| 规则 | 要求 |
|------|------|
| 共享组件 | 必须创建 `.stories.ts` 文件 |
| Props 展示 | Stories 必须展示所有 props |

---

## 代码复用

实现功能前必须先搜索现有实现：

| 复用场景 | 搜索关键词 | 复用目标 |
|----------|------------|----------|
| SSE 流式 | `SSE`, `stream`, `chatSSE` | `ai_assistant_api` |
| 权限检查 | `permission`, `has_permission` | `usePermissionStore` |

---

## 禁止行为汇总

| 禁止 | 原因 |
|------|------|
| TypeScript 四禁令 | 违反类型安全 |
| Props/State 使用 any | 违反类型安全 |
| 内联定义类型 | 违反单一来源 |
| 直接解构 State | 失去响应性 |
| 硬编码 baseURL | 环境不一致 |

---

**详细参考**：`CRM-Client/docs/TYPESCRIPT.md`, `CRM-Client/docs/COMPONENTS.md`, `CRM-Client/docs/STATE-MANAGEMENT.md`