# AI 知识沉淀 - CRMWolf

**用途**：记录 AI 常见错误、优秀案例、可复用模式，避免重复踩坑

---

## 一、常见错误（禁止重复）

### 1.1 TypeScript 类型错误

| 错误做法 | 正确做法 | 参考 |
|----------|----------|------|
| `const data: any = response` | 从 TYPESCRIPT.md 导入类型 + Zod 校验 | TYPESCRIPT.md §二 |
| `const res = api.get() as any` | 使用 Approved Types + `.parse()` | TYPESCRIPT.md §1.2 |
| `// @ts-ignore` | 修复错误源，不隐藏 | TYPESCRIPT.md §1.3 |
| `customer.value!.id` | `customer.value?.id` + 条件判断 | TYPESCRIPT.md §1.4 |

### 1.2 架构错误

| 错误做法 | 正确做法 | 参考 |
|----------|----------|------|
| 组件内直接调用 API | 通过 props/emit，由页面调用 | ARCHITECTURE.md §四 |
| views 内定义类型 | 从 schemas/ 导入 | ARCHITECTURE.md §三 |
| 跨层导入（api 导入 stores） | 通过参数传递 | ARCHITECTURE.md §四 |
| 组件局部状态用 Store | 使用 ref 在组件内管理 | STATE-MANAGEMENT.md §七 |

### 1.3 测试错误

| 错误做法 | 正确做法 | 参考 |
|----------|----------|------|
| 跳过测试 `.skip` | 必须完成所有测试 | TESTING.md §六 |
| Mock 数据使用 any | 使用 TYPESCRIPT.md 类型 | TESTING.md §1.1 |
| 不写测试直接提交 | 先写测试再写代码 | TESTING.md §六 |

### 1.4 文档错误

| 错误做法 | 正确做法 | 参考 |
|----------|----------|------|
| 只改代码不改文档 | 同 PR 更新对应文档 | DOCS-STANDARD.md §一 |
| 自创权限码/状态值 | 在 GLOSSARY.md 查找 | GLOSSARY.md §七 |

---

## 二、优秀案例

### 2.1 类型安全 API 调用

```typescript
// ✅ 正确示例
import { CustomerListResponseSchema, type CustomerResponse } from '@/schemas/customer'
import { customerApi } from '@/api/customer'

const fetchCustomers = async (): Promise<CustomerResponse[]> => {
  const raw = await customerApi.getList({ page: 1, pageSize: 20 })
  const validated = CustomerListResponseSchema.parse(raw)
  return validated.data
}
```

### 2.2 类型安全 Vue 组件

```typescript
// ✅ 正确示例
const props = defineProps({
  customer: {
    type: Object as PropType<CustomerResponse>,
    required: true
  }
})

const emit = defineEmits<{
  (e: 'update', value: CustomerCreate): void
}>()
```

### 2.3 类型安全 Pinia Store

```typescript
// ✅ 正确示例
const items = ref<CustomerResponse[]>([])
const loading = ref<boolean>(false)

const currentItem = computed<CustomerResponse | null>(() => {
  return items.value.find(i => i.id === currentId.value) ?? null
})

const fetchList = async (): Promise<void> => {
  loading.value = true
  try {
    const validated = CustomerListResponseSchema.parse(await api.getList())
    items.value = validated.data
  } catch (e) {
    error.value = e instanceof Error ? e.message : '未知错误'
  } finally {
    loading.value = false
  }
}
```

---

## 三、可复用模式

### 3.1 分页请求模式

```typescript
interface PaginationParams {
  page: number
  pageSize: number
}

interface PaginatedResponse<T> {
  data: T[]
  total: number
  page: number
  pageSize: number
}

// Store 使用
const fetchPaginated = async <T>(
  apiCall: (params: PaginationParams) => Promise<PaginatedResponse<T>>,
  page: number,
  pageSize: number
): Promise<void> => {
  loading.value = true
  try {
    const result = await apiCall({ page, pageSize })
    items.value = result.data
    total.value = result.total
  } finally {
    loading.value = false
  }
}
```

### 3.2 错误处理模式

```typescript
// 统一错误处理
const handleApiError = (e: unknown): string => {
  if (e instanceof Error) {
    return e.message
  }
  if (typeof e === 'string') {
    return e
  }
  return '未知错误'
}

// Store 中使用
try {
  // API call
} catch (e) {
  error.value = handleApiError(e)
}
```

### 3.3 权限检查模式

```typescript
import { usePermissionsStore } from '@/stores/permissions'

const permissionsStore = usePermissionsStore()

const canEdit = computed<boolean>(() => {
  return permissionsStore.hasPermission('customer:update')
})

const canViewAll = computed<boolean>(() => {
  return permissionsStore.hasPermission('customer:view_all')
})
```

---

## 四、FAQ

### Q1: API 返回类型未定义怎么办？
**A**: 查看 TYPESCRIPT.md §二 Approved Types，如果不存在，需要：
1. 查看后端 schemas/*.py 对应 Schema
2. 在 TYPESCRIPT.md 新增类型定义
3. 在 src/schemas/ 创建 Zod Schema
4. 提交审批

### Q2: 类型错误无法修复怎么办？
**A**:
1. 不要使用 any/as/@ts-ignore/!
2. 使用 COMPLIANCE-STANDARD.md 模板报告
3. 等待人工审批

### Q3: 现存代码有 any 怎么办？
**A**: 查看 .compliance-baseline.json，按清理计划处理：
- Week 5-6: stores/ + api/
- Week 7-8: components/
- Week 9-12: views/

### Q4: 新增权限码怎么办？
**A**:
1. 查看权限格式规范：GLOSSARY.md §一
2. 在 GLOSSARY.md 提出新增申请
3. 人工审批后添加

---

## 五、知识更新规则

| 规则 | 要求 |
|------|------|
| 新错误发现 | 必须添加到 §一 |
| 优秀代码模式 | 必须添加到 §二/§三 |
| FAQ 更新 | 遇到新问题必须添加 |
| 人工审批 | 新增内容需人工确认 |

---

**版本：1.0 | 最后更新：2026-04-21**