# Harness 规范体系 - 快速上手指南

**目标**：5 分钟内掌握 CRMWolf 开发规范

---

## 一、第一步：阅读 AGENTS.md

**位置**：`/AGENTS.md`

这是 AI + 团队的唯一行为入口，包含：
- 红线锁定（不可突破）
- 规范导航索引
- 校验流程说明

**阅读时间**：1 分钟

---

## 二、第二步：根据任务查规范

| 任务类型 | 查阅文档 | 关键内容 |
|----------|----------|----------|
| 新增 API | TYPESCRIPT.md → system/ARCHITECTURE.md | Approved Types + api/ 目录规则 |
| 新增页面 | COMPONENTS.md → system/GLOSSARY.md | 组件模板 + 状态枚举 |
| 新增 Store | STATE-MANAGEMENT.md | Store 模板 + ref 类型规则 |
| 写单测 | TESTING.md | 测试模板 + Mock 数据规则 |
| 修复类型错误 | TYPESCRIPT.md §一 | 四禁令替代方案 |
| 查业务流程 | system/SYSTEM-DESCRIPTION.md | 功能模块、业务逻辑 |
| 查 API 接口 | system/BUSINESS-CHAIN-API.md | 接口清单、参数说明 |

**阅读时间**：2 分钟

---

## 三、第三步：使用模板开发

### 3.1 Vue 组件模板

```vue
<script setup lang="ts">
// 1. 导入（字母序）
import { computed, ref } from 'vue'
import type { PropType } from 'vue'

// 2. 类型导入（从 schemas/）
import type { CustomerResponse } from '@/schemas/customer'

// 3. Props（必须类型化）
const props = defineProps({
  customer: {
    type: Object as PropType<CustomerResponse>,
    required: true
  }
})

// 4. Emits（必须类型化）
const emit = defineEmits<{
  (e: 'update', value: CustomerCreate): void
}>()

// 5. 本地状态（必须类型化）
const loading = ref<boolean>(false)
</script>
```

### 3.2 API 调用模板

```typescript
// api/customer.ts
import request from '@/utils/request'
import { CustomerListResponseSchema, type CustomerResponse } from '@/schemas/customer'

export const customerApi = {
  async getList(params: PaginationParams): Promise<CustomerListResponse> {
    const raw = await request.get('/api/v1/customers', { params })
    return CustomerListResponseSchema.parse(raw)  // Zod 校验
  }
}
```

### 3.3 Pinia Store 模板

```typescript
// stores/customer.ts
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { CustomerResponse } from '@/schemas/customer'

export const useCustomerStore = defineStore('customer', () => {
  const items = ref<CustomerResponse[]>([])  // 必须类型化
  const loading = ref<boolean>(false)

  const fetchList = async (): Promise<void> => {
    loading.value = true
    try {
      const result = CustomerListResponseSchema.parse(await customerApi.getList())
      items.value = result.data
    } finally {
      loading.value = false
    }
  }

  return { items, loading, fetchList }
})
```

---

## 四、第四步：提交前校验

```bash
# 前端
npm run lint          # ESLint 校验
npm run type-check    # TypeScript 校验
npm run test:unit     # 单测

# 后端
ruff check app/       # Python lint
mypy app/             # 类型检查
pytest tests/unit -v  # 单测
```

---

## 五、第五步：CI 通过后合并

CI Pipeline 自动执行：
1. ESLint + TypeScript 检查
2. 单测 + 覆盖率检查
3. 合规检查（新增文件零违规）
4. 文档同步检查

---

## 六、常见问题

### Q1: 类型报错怎么办？
**不要使用**：`any` / `as any` / `@ts-ignore` / `!`

**正确做法**：
1. 查看 TYPESCRIPT.md §一（替代方案）
2. 从 schemas/ 导入类型
3. 使用 Zod 校验

### Q2: 找不到类型定义怎么办？
1. 查看 TYPESCRIPT.md §二（Approved Types）
2. 查看对应后端 schemas/*.py
3. 在 schemas/ 创建 Zod Schema

### Q3: 配置文件报错怎么办？
配置文件被锁定，修改需人工审批：
1. 填写 SPEC-CHANGELOG.md 变更申请
2. 提交审批
3. 审批通过后修改

---

## 七、红线提醒

| 红线 | 违规后果 |
|------|----------|
| 使用 `any` | ESLint 阻止提交 |
| 使用 `as any` | ESLint 阻止提交 |
| 使用 `@ts-ignore` | ESLint 阻止提交 |
| 使用 `!` 非空断言 | ESLint 阻止提交 |
| 修改配置文件 | Git hooks 阻止提交 |
| 不写单测 | pre-push 阻止推送 |

---

**完成时间**：≤5 分钟

**下一步**：开始开发 → 遇到问题查对应规范 → 提交前校验 → CI 通过合并