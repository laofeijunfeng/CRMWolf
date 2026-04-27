# Pinia 状态管理规范 - CRMWolf

**适用范围**：CRM-Client/src/stores

---

## 一、Store 模板（强制结构）

```typescript
// stores/customer.ts
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { CustomerResponse, CustomerCreate } from '@/schemas/customer'
import { CustomerListResponseSchema } from '@/schemas/customer'
import { customerApi } from '@/api/customer'

export const useCustomerStore = defineStore('customer', () => {
  // ===== 1. State（必须类型化） =====
  const items = ref<CustomerResponse[]>([])
  const loading = ref<boolean>(false)
  const error = ref<string | null>(null)
  const currentId = ref<number | null>(null)
  const total = ref<number>(0)

  // ===== 2. Computed（必须返回类型） =====
  const currentItem = computed<CustomerResponse | null>(() => {
    return items.value.find(item => item.id === currentId.value) ?? null
  })

  const hasItems = computed<boolean>(() => {
    return items.value.length > 0
  })

  // ===== 3. Actions（必须参数和返回类型） =====
  const fetchList = async (page: number = 1, pageSize: number = 20): Promise<void> => {
    loading.value = true
    error.value = null

    try {
      const raw = await customerApi.getList({ page, pageSize })
      // Zod 校验
      const validated = CustomerListResponseSchema.parse(raw)
      items.value = validated.data
      total.value = validated.total
    } catch (e) {
      error.value = e instanceof Error ? e.message : '获取客户列表失败'
    } finally {
      loading.value = false
    }
  }

  const fetchById = async (id: number): Promise<CustomerResponse | null> => {
    loading.value = true
    error.value = null

    try {
      const raw = await customerApi.getById(id)
      const validated = CustomerResponseSchema.parse(raw)
      currentId.value = validated.id
      return validated
    } catch (e) {
      error.value = e instanceof Error ? e.message : '获取客户详情失败'
      return null
    } finally {
      loading.value = false
    }
  }

  const create = async (data: CustomerCreate): Promise<CustomerResponse | null> => {
    loading.value = true
    error.value = null

    try {
      const raw = await customerApi.create(data)
      const validated = CustomerResponseSchema.parse(raw)
      items.value.push(validated)
      return validated
    } catch (e) {
      error.value = e instanceof Error ? e.message : '创建客户失败'
      return null
    } finally {
      loading.value = false
    }
  }

  const clear = (): void => {
    items.value = []
    currentId.value = null
    error.value = null
    total.value = 0
  }

  // ===== 4. 返回所有导出 =====
  return {
    // State
    items,
    loading,
    error,
    currentId,
    total,
    // Computed
    currentItem,
    hasItems,
    // Actions
    fetchList,
    fetchById,
    create,
    clear
  }
})
```

---

## 二、State 规范

| 规则 | 要求 |
|------|------|
| 类型声明 | 必须 `ref<Type>(...)` |
| 初始值 | 必须提供正确的初始值 |
| 禁止 any | State 禁止使用 any 类型 |

### 2.1 基本类型

```typescript
// 正确
const loading = ref<boolean>(false)
const count = ref<number>(0)
const name = ref<string>('')

// 禁止
const loading = ref(false)  // 无类型
const data = ref<any>(null)  // 使用 any
```

### 2.2 数组类型

```typescript
// 正确
const items = ref<CustomerResponse[]>([])
const ids = ref<number[]>([])

// 禁止
const items = ref([])  // 无类型
```

### 2.3 可空类型

```typescript
// 正确
const error = ref<string | null>(null)
const currentId = ref<number | null>(null)

// 禁止
const error = ref(null)  // 无类型
```

---

## 三、Computed 规范

| 规则 | 要求 |
|------|------|
| 返回类型 | 必须 `computed<Type>(() => ...)` |
| 禁止副作用 | Computed 禁止修改其他状态 |

```typescript
// 正确
const displayName = computed<string>(() => {
  return currentItem.value?.account_name ?? '未选择'
})

// 禁止
const displayName = computed(() => {  // 无返回类型
  loading.value = true  // 副作用
  return currentItem.value?.account_name
})
```

---

## 四、Actions 规范

| 规则 | 要求 |
|------|------|
| 参数类型 | 必须声明每个参数类型 |
| 返回类型 | 必须声明返回类型 |
| 异步标记 | async 函数必须返回 Promise |
| 错误处理 | 必须使用 try-catch |

```typescript
// 正确
const fetchById = async (id: number): Promise<CustomerResponse | null> => {
  try {
    // ...
  } catch (e) {
    error.value = e instanceof Error ? e.message : '未知错误'
    return null
  }
}

// 禁止
const fetchById = async (id) => {  // 无参数类型
  // 无 try-catch
}
```

---

## 五、Store 使用规范

### 5.1 在组件中使用

```typescript
// 正确
import { useCustomerStore } from '@/stores/customer'
import { storeToRefs } from 'pinia'

const customerStore = useCustomerStore()
const { items, loading, error } = storeToRefs(customerStore)
const { fetchList } = customerStore

// 调用 action
await fetchList()
```

### 5.2 解构规则

```typescript
// 正确 - State/Computed 使用 storeToRefs
const { items, loading, currentItem } = storeToRefs(store)

// 正确 - Actions 直接解构
const { fetchList, create } = store

// 禁止 - State 直接解构（失去响应性）
const { items } = store  // 错误
```

---

## 六、现有 Store 文档

### 6.1 user.ts

```typescript
// 已有 Store，待类型修复
export const useUserStore = defineStore('user', () => {
  // State
  const user: UserInfo | null = ref(null)  // 待修复：添加类型
  const token: string | null = ref(null)
  const roles: string[] = ref([])
  const permissions: string[] = ref([])

  // Actions
  const login = async (...): Promise<void> => { ... }
  const logout = (): void => { ... }
})
```

### 6.2 permissions.ts

```typescript
// 已有 Store，待类型修复
export const usePermissionsStore = defineStore('permissions', () => {
  const permissions: string[] = ref([])

  const hasPermission = (code: string): boolean => {
    return permissions.value.includes(code)
  }
})
```

---

## 七、Store 组织规则

| 规则 | 要求 |
|------|------|
| 命名 | lowercase.ts（如 customer.ts） |
| 单一领域 | 一个 Store 管理一个业务领域 |
| 禁止全局状态滥用 | 组件局部状态不用 Store |

---

## 八、禁止行为

| 禁止 | 原因 |
|------|------|
| State 使用 any | 违反类型安全 |
| Computed 有副作用 | 违反 Computed 定义 |
| 直接解构 State | 失去响应性 |
| 组件局部状态用 Store | 过度使用全局状态 |

---

## 九、校验规则

| 校验点 | 工具 | 时机 |
|--------|------|------|
| State 类型 | ESLint 检测 ref<any> | pre-commit |
| Computed 返回类型 | TypeScript compiler | pre-commit |
| Actions 类型 | TypeScript compiler | pre-commit |

---

**版本：1.0 | 最后更新：2026-04-21 | 修改需人工审批**