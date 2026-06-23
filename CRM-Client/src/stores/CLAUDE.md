# Pinia Store 专属约束

**Claude Code 进入此目录时自动加载**

---

## State 规范

| 规则 | 要求 |
|------|------|
| 类型声明 | 必须 `ref<Type>(...)` |
| 禁止 any | State 禁止使用 any 类型 |
| 初始值 | 必须提供正确的初始值 |

```typescript
// 正确
const loading = ref<boolean>(false)
const items = ref<CustomerResponse[]>([])

// 禁止
const loading = ref(false)  // 无类型
const data = ref<any>(null)  // 使用 any
```

---

## Computed 规范

| 规则 | 要求 |
|------|------|
| 返回类型 | 必须 `computed<Type>(() => ...)` |
| 禁止副作用 | Computed 禁止修改其他状态 |

---

## Actions 规范

| 规则 | 要求 |
|------|------|
| 参数类型 | 必须声明每个参数类型 |
| 返回类型 | 必须声明返回类型 |
| 异步标记 | async 函数必须返回 Promise |
| 错误处理 | 必须使用 try-catch |

---

## SSE 状态管理

| 规则 | 要求 |
|------|------|
| SSE 连接 | 使用统一的 SSE parser |
| 状态更新 | 按事件类型更新对应状态 |
| 错误处理 | 必须处理 SSE 连接失败 |

---

## 解构规则

```typescript
// 正确 - State/Computed 使用 storeToRefs
const { items, loading } = storeToRefs(store)

// 禁止 - State 直接解构（失去响应性）
const { items } = store
```

---

## Store 命名规范

| 规则 | 要求 |
|------|------|
| 文件命名 | lowercase.ts（如 `customer.ts`） |
| Store 命名 | `use[Domain]Store`（如 `useCustomerStore`） |
| 单一领域 | 一个 Store 理一个业务领域 |

---

**详细规范**：`CRM-Client/docs/STATE-MANAGEMENT.md`