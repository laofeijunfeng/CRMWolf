---
priority: high
status: active
---

# TypeScript 类型系统规范 - CRMWolf

**适用范围**：CRM-Client/src 所有 .ts 和 .vue 文件

**权威说明**：本文档是 TypeScript 类型定义的单一事实来源，其他文档仅允许引用，禁止重新定义类型。

---

## 一、四禁令（零妥协）

| 禁令 | 检测规则 | 曝光后果 | 替代方案 |
|------|----------|----------|----------|
| `: any` | ESLint `no-any-type` | 阻止提交 | 使用本文档 Approved Types |
| `as any` | ESLint `no-as-any` | 阻止提交 | 使用本文档 Approved Types |
| `@ts-ignore` | ESLint `no-ts-ignore` | 阻止提交 | 修复错误源，不隐藏 |
| `!` 非空断言 | ESLint `no-non-null` | 阻止提交 | 使用条件判断或 Optional |

### 1.1 禁用 `: any` 的替代方案

```typescript
// 禁止
const params: any = { page: 1 }
const error: any = e

// 正确 - 使用具体类型
const params: PaginationParams = { page: 1, pageSize: 20 }
const error: Error = e instanceof Error ? e : new Error(String(e))
```

### 1.2 禁用 `as any` 的替代方案

```typescript
// 禁止
const response = await api.getCustomers() as any

// 正确 - 使用 Approved Types + Zod 校验
const response = await api.getCustomers()
const validated = CustomerListResponseSchema.parse(response)
```

### 1.3 禁用 `@ts-ignore` 的替代方案

```typescript
// 禁止
// @ts-ignore
someUntypedFunction()

// 正确 - 为函数添加类型声明
function someTypedFunction(): void { ... }
someTypedFunction()
```

### 1.4 禁用 `!` 非空断言的替代方案

```typescript
// 禁止
const id = customer.value!.id

// 正确 - 使用条件判断
const id = customer.value?.id
if (id === undefined) {
  throw new Error('Customer not loaded')
}
```

---

## 二、Approved Types 清单

### 2.1 分页类型

```typescript
// src/schemas/common.ts
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
```

### 2.2 用户类型

```typescript
// 映射后端 schemas/customer.py OwnerInfo
interface UserInfo {
  id: string           // 飞书 Open ID
  name: string
  avatar_url: string | null
}

// 当前用户状态（stores/user.ts）
interface UserState {
  user: UserInfo | null
  token: string | null
  roles: string[]
  permissions: string[]
}
```

### 2.3 客户类型

```typescript
// 映射后端 schemas/customer.py
type CustomerStatus = '0' | '1' | '2' | '3'  // 跟进中|已成交|已流失|非激活

interface CustomerResponse {
  id: number
  account_name: string
  industry: string | null
  city: string
  address: string | null
  company_scale: string | null
  source: string | null
  status: CustomerStatus
  owner_id: string | null
  source_lead_id: number | null
  default_procurement_method_id: number | null
  return_reason: string | null
  returned_time: string | null  // ISO datetime
  creator_id: string
  created_time: string          // ISO datetime
  last_modified_time: string    // ISO datetime
  version: number
}

interface CustomerListResponse extends CustomerResponse {
  owner_info: UserInfo | null
  creator_info: UserInfo | null
}

interface CustomerCreate {
  account_name: string
  industry?: string
  city: string
  address?: string
  company_scale?: string
  source?: string
  owner_id?: string
  default_procurement_method_id?: number
}
```

### 2.4 线索类型

```typescript
// 映射后端 schemas/lead.py
type LeadSource =
  | 'WEBSITE' | 'REFERRAL' | 'EVENT' | 'COLD_CALL'
  | 'WEBSITE_INQUIRY' | 'EXHIBITION' | 'OTHER'

type LeadStatus =
  | 'NEW' | 'CONTACTED' | 'QUALIFIED' | 'CONVERTED' | 'INVALID'

type CompanyScale =
  | '1-10' | '11-50' | '51-200' | '201-500' | '500+'

interface LeadResponse {
  id: number
  lead_name: string
  source: LeadSource
  city: string
  contact_name: string
  contact_phone: string
  company_scale: CompanyScale | null
  owner_id: string | null
  status: LeadStatus
  pool_id: number | null
  creator_id: string
  created_time: string
  last_modified_time: string
  version: number
}

interface LeadListResponse extends LeadResponse {
  owner_info: UserInfo | null
}
```

### 2.5 API 响应类型

```typescript
// 所有 API 返回必须使用 PaginatedResponse 包装
interface ApiSuccessResponse<T> {
  success: true
  data: T
}

interface ApiErrorResponse {
  success: false
  error: {
    code: string
    message: string
  }
}
```

### 2.6 SSE 流式事件类型

```typescript
// SSE (Server-Sent Events) 流式响应类型
// 定义位置：src/utils/sseParser.ts

/**
 * SSE 事件类型枚举
 */
type SSEEventType =
  | 'status'              // 状态消息
  | 'content'             // 内容增量
  | 'context_summary'     // 上下文汇总
  | 'react_start'         // ReAct 循环开始
  | 'round_start'         // 轮次开始
  | 'tool_call'           // 工具调用
  | 'tool_result'         // 工具执行结果
  | 'waiting_for_user'    // 等待用户回复（关键：Human-in-the-Loop）
  | 'parsed'              // 解析完成
  | 'parsed_multi'        // 多工具解析
  | 'result'              // 最终结果
  | 'error'               // 错误
  | 'react_complete'      // ReAct 循环完成
  | 'round_completed'     // 单轮完成
  | 'max_rounds_reached'  // 达到最大轮数

/**
 * SSE 事件结构
 * 注：后端可能直接在顶层返回字段，而不是嵌套在 data 中
 */
interface SSEEvent {
  event: SSEEventType

  // 顶层字段（后端可能直接返回）
  session_id?: string
  question?: string
  options?: string[] | null
  missing_fields?: string[]
  field_options?: Record<string, FieldOptionConfig>
  context_hint?: string

  // ReAct 循环相关
  round?: number
  max_rounds?: number
  tool?: string
  params?: Record<string, unknown>
  result?: ToolResult
  previous_results?: ToolResult[]

  // Workflow 相关
  data?: WorkflowEventData

  // 结果相关
  success?: boolean
  message?: string
  reply_text?: string
  content?: string
}

/**
 * 字段选项配置（用于动态表单渲染）
 */
interface FieldOptionConfig {
  type: 'select' | 'text' | 'number' | 'date' | 'textarea'
  options?: string[]
  default?: string
  placeholder?: string
}

/**
 * 工具执行结果
 */
interface ToolResult {
  tool: string
  success: boolean
  message?: string
  data?: unknown
}

/**
 * Workflow 事件数据
 */
interface WorkflowEventData {
  session_id?: string
  step_id?: string
  workflow_name?: string
  description?: string
  success?: boolean
  message?: string
  error?: string
  result?: Record<string, unknown>
  question?: string
  options?: string[]
  missing_fields?: string[]
  field_options?: Record<string, FieldOptionConfig>
}
```

---

## 三、类型创建规则

| 规则 | 要求 |
|------|------|
| 新类型创建 | 必须先更新本文档，获得审批 |
| 类型复用 | 使用 intersection `&`，禁止重复定义 |
| 后端同步 | 前端类型必须映射后端 Pydantic schema |
| Zod 校验 | 所有 API 响应类型必须有对应 Zod schema |

### 3.1 类型同步流程

```
后端 Pydantic Schema  →  前端 TypeScript Interface  →  前端 Zod Schema
     (schemas/*.py)           (TYPESCRIPT.md)              (src/schemas/*.ts)
```

**必须同步更新**：
1. 后端 schema 修改 → 前端类型 + Zod schema 同步更新
2. 前端新类型 → 后端 schema 同步创建
3. 所有变更记录到 DOCS-STANDARD.md

---

## 四、现存违规清单（待修复）

| 文件 | 违规类型 | 数量 | 状态 |
|------|----------|------|------|
| src/stores/user.ts | `: any` | 2 | 待修复 |
| src/stores/permissions.ts | `: any` | 1 | 待修复 |
| src/views/Customers.vue | `: any` | 7 | 待修复 |
| src/views/CustomerDetail.vue | `as any` | 16 | 待修复 |
| src/api/*.ts | `as any` | 40+ | 待修复 |

**修复优先级**：
1. stores/*.ts（Week 5）
2. api/*.ts（Week 5）
3. components/*.vue（Week 7）
4. views/*.vue（Week 9-12）

---

## 五、校验规则

| 校验点 | 工具 | 时机 |
|--------|------|------|
| 四禁令检测 | ESLint custom rules | pre-commit |
| 类型完整性 | TypeScript compiler | pre-commit |
| Zod 校验覆盖 | ESLint `require-zod-schema` | pre-commit |

---

**版本：1.1 | 最后更新：2026-06-11 | 修改需人工审批**