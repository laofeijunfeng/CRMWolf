---
status: approved
created: 2026-06-22
updated: 2026-06-22
priority: high
type: feature
---

# AI 助手思考执行过程显示需求

**需求性质**：Feature（新增前端组件）  
**优先级**：High（用户体验核心功能）  
**状态**：已批准并实施  

---

## 一、需求背景

### 1.1 问题分析

当前 AI 助手在执行复杂操作时，用户只能看到最终结果，无法了解中间过程：

| 问题 | 影响 |
|------|------|
| **透明度不足** | 用户不知道 AI "为什么这么做"，信任感弱 |
| **等待焦虑** | 长时间执行时，用户不知道进度，可能误以为卡死 |
| **错误难以定位** | 执行失败时，用户无法理解失败原因 |
| **技术化表达** | 当前显示 "tool_call", "keyword = ..." 等技术名词，用户困惑 |

### 1.2 目标用户

- **销售人员**：主要使用者，不理解技术术语
- **客户经理**：需要透明过程建立信任
- **管理层**：需要理解 AI 操作流程

### 1.3 核心目标

**透明展示 AI 执行过程，建立用户信任感**

---

## 二、需求讨论记录（2026-06-22）

### 2.1 Question 1：功能定位

**选项**：
- A) 完整推理过程 - AI 的每一步思考、工具调用、结果
- B) 仅关键步骤 - 只显示重要操作（创建、更新、删除）
- C) 仅最终结果 - 保持现状

**用户选择**：**A（完整推理过程）**
- 强调"很强的可读性，业务友好"

### 2.2 Question 2：展示时机

**选项**：
- A) 实时流式显示 - AI 执行时同步展示
- B) 执行后一次性展示 - 完成后显示全部过程
- C) 可选查看 - 用户点击后才显示

**用户选择**：**A（实时流式显示）**
- 用户能看到"正在做..."，增强透明感

### 2.3 Question 3：内容层级

**选项**：
- A) 仅业务信息 - 只显示业务化表达
- B) 业务信息 + 技术细节 - 分层展示，默认业务信息
- C) 仅技术细节 - 开发者视角

**用户选择**：**B（业务信息 + 技术细节分层）**
- L1：业务信息（默认显示）
- L2：技术细节（可选展开）

### 2.4 Question 4：默认收起状态内容

**选项**：
- A) 当前步骤状态 - "正在搜索客户..."
- B) 进度指示器 - "Round 1/5" + 进度条
- C) 简化摘要 - "正在处理，已完成 3 步..."
- D) 动态状态图标 - ⟳ 旋转图标 + "正在执行..."

**用户选择**：**A + D（当前步骤状态 + 动态图标）**

### 2.5 Question 5：思考气泡设计

**选项**：
- A) 极简灰色卡片 - 浅灰背景 + 斜体文字 + CPU 图标
- B) 微蓝卡片 - 微蓝背景 + 正常文字 + CPU 图标
- C) 对话气泡 - 圆角气泡 + 灰色背景 + 引号标记
- D) 代码块风格 - 等宽字体 + 浅灰背景 + 边框

**用户选择**：**A + B（极简灰色卡片 + 微蓝背景）**
- Signature Element：微蓝背景 + 斜体 + CPU 图标

---

## 三、实现方案对比

### 3.1 方案 A：最小实现 - 直接复用 StatusCard

| 维度 | 评估 |
|------|------|
| 开发工作量 | ✅ 最小（0 新组件） |
| 设计自由度 | ❌ 思考气泡样式受限 |
| 业务化表达 | ❌ 无法完全实现 |
| 用户体验 | ❌ 技术名词暴露，信任感不足 |

**结论**：不推荐

### 3.2 方案 B：推荐方案 - ThinkingBubble + StatusCard

| 维度 | 评估 |
|------|------|
| 开发工作量 | ✅ 适中（100 行代码） |
| 设计自由度 | ✅ 思考气泡完全可控 |
| 业务化表达 | ✅ "正在搜索：光大证券" |
| 用户体验 | ✅ 信任感强，不干扰 |
| 一致性 | ✅ 复用 StatusCard，遵循 Design Token |

**结论**：✅ **推荐方案**（用户选择）

### 3.3 方案 C：完全重构

| 维度 | 评估 |
|------|------|
| 开发工作量 | ❌ 最大（300+ 行） |
| 设计自由度 | ✅ 最高 |
| 一致性 | ❌ 可能违反 Design Token |

**结论**：过度设计，不推荐

---

## 四、方案 B 详细设计

### 4.1 组件架构

```
MagicWandDialog.vue（现有）
  └─> AgentExecutionLog.vue（新增，容器组件）
       ├─> CollapsedHeader（收起状态）
       │    ├─> <Loading /> 图标
       │    ├─> 当前步骤文本
       │    └─> <ArrowDown /> 图标（点击展开）
       │
       └─> ExpandedContent（展开状态）
            ├─> ThinkingBubble.vue（新增）
            ├─> StatusCard.vue（复用）
            └─> BusinessParams（业务参数格式化）
```

### 4.2 文件结构

```
CRM-Client/src/
  ├── components/
  │   ├── ThinkingBubble.vue       （新增，30行）
  │   ├── AgentExecutionLog.vue    （新增，80行）
  │   ├── StatusCard.vue           （复用，无需修改）
  │   └── MagicWandDialog.vue      （修改，集成）
  │
  ├── composables/
  │   └── useAgentExecutionLog.ts  （新增，40行）
  │
  ├── types/
  │   └── agentExecution.ts        （新增，类型定义）
  │
  └── components/__tests__/
      ├── ThinkingBubble.test.ts   （新增）
      ├── AgentExecutionLog.test.ts（新增）
      └── useAgentExecutionLog.test.ts（新增）
```

### 4.3 ThinkingBubble 组件设计

**Props**：
```typescript
interface ThinkingBubbleProps {
  content: string  // AI 推理过程文本
}
```

**视觉设计**：
| 属性 | 值 | 说明 |
|------|-----|------|
| 背景 | `$wolf-bg-ai-message` (#F0F4F8) | 微蓝，暗示智能 |
| 图标 | `<Cpu />` | 品牌一致 |
| 字体 | 斜体 | 传达"思考过程" |
| 字号 | 13px | 辅助信息层级 |
| 字色 | `$wolf-text-secondary` | 不干扰 |
| 圆角 | 4px | 克制设计 |

### 4.4 AgentExecutionLog 容器组件设计

**收起状态**：
```
┌─────────────────────────────────┐
│ [⟳] 正在搜索客户...             │ ← 当前步骤 + 旋转图标
│ [点击展开查看详细过程]           │ ← 提示可展开
└─────────────────────────────────┘
```

**展开状态**：
```
┌─────────────────────────────────┐
│ [收起] ▲                        │
│                                 │
│ Round 1                         │
│ ┌───────────────────────┐       │
│ │ [CPU] 用户想跟进光大证券，│     │ ← 思考气泡
│ │      需要先找到客户...   │     │
│ └───────────────────────┘       │
│                                 │
│ 正在搜索："光大证券"             │ ← 业务参数
│                                 │
│ ✓ 找到 5 个客户                  │ ← 结果摘要
└─────────────────────────────────┘
```

### 4.5 SSE 事件映射逻辑

| SSE 事件 | 执行步骤 | 显示内容 |
|----------|----------|----------|
| `react_start` | REACT_START | 初始化日志 |
| `round_start` | ROUND_START | 显示轮次分隔 |
| `tool_call` | TOOL_CALL | 思考气泡 + 业务参数 |
| `tool_result` | TOOL_RESULT | 结果摘要 |
| `react_complete` | REACT_COMPLETE | 完成状态 |
| `waiting_for_user` | WAITING_FOR_USER | 自动展开 |
| `error` | ERROR | 错误提示 |

### 4.6 工具名称业务化映射

| 技术名称 | 业务化标题 |
|----------|------------|
| `search_customer` | 查找客户信息 |
| `create_customer` | 创建客户 |
| `update_customer` | 更新客户信息 |
| `delete_customer` | 删除客户 |
| `search_opportunity` | 查找商机信息 |
| `create_follow_up` | 创建跟进记录 |
| `win_opportunity` | 标记商机为赢单 |
| ... | ... |

---

## 五、错误处理设计

### 5.1 SSE 连接错误

```typescript
case 'error':
  // 显示错误状态卡片
  executionLog.value.steps.push({
    type: 'error',
    title: '执行失败',
    description: event.message || '连接中断，请重试'
  })
  // 自动收起（避免干扰）
  executionLog.value.expanded = false
```

### 5.2 工具执行失败

```typescript
case 'tool_result':
  if (!event.result?.success) {
    // 失败步骤：显示错误提示 + 解决建议
    executionLog.value.steps[stepIndex] = {
      ...step,
      status: 'error',
      suggestion: getSuggestion(event.tool, event.result?.message)
    }
  }
```

**错误提示 + 解决建议映射**：

| 场景 | 错误信息 | 解决建议 |
|------|----------|----------|
| 客户未找到 | "未找到" | "建议：请提供更精确的客户名称" |
| 客户不存在 | "客户不存在" | "建议：请先创建客户记录" |
| 商机不存在 | "商机不存在" | "建议：请先创建商机" |

### 5.3 Human-in-the-Loop 处理

```typescript
case 'waiting_for_user':
  // 自动展开（需要用户关注）
  executionLog.value.expanded = true
  executionLog.value.steps.push({
    type: 'waiting_for_user',
    title: '等待您的回复',
    description: event.question
  })
```

---

## 六、测试策略

### 6.1 覆盖率要求

遵循 CRMWolf 测试规范：**新组件覆盖率 100%**

### 6.2 测试用例清单

| 组件 | 测试用例 |
|------|----------|
| **ThinkingBubble** | 渲染 CPU 图标、显示斜体文字、使用微蓝背景、遵循 Design Token |
| **AgentExecutionLog** | 默认收起状态、点击展开、显示思考气泡、业务参数格式化、轮次分隔线、复用 StatusCard |
| **useAgentExecutionLog** | tool_call 事件映射、tool_result 更新状态、工具名称业务化映射、SSE 连接错误、等待用户自动展开 |

### 6.3 业务化验证

关键验证点：
```typescript
// 确保"keyword ="不出现
expect(paramsElement.text()).not.toContain('keyword =')

// 确保业务化表达
expect(paramsElement.text()).toContain('正在搜索："光大证券"')
```

---

## 七、开发工作量估算

| 组件/文件 | 代码量 | 时间 |
|-----------|--------|------|
| ThinkingBubble.vue | 30 行 | 30 分钟 |
| AgentExecutionLog.vue | 80 行 | 1 小时 |
| useAgentExecutionLog.ts | 40 行 | 45 分钟 |
| agentExecution.ts | 50 行 | 30 分钟 |
| 测试文件 | 150 行 | 1 小时 |
| **总计** | **350 行** | **3.5 小时** |

---

## 八、设计决策记录

| 决策 | 选择 | 原因 |
|------|------|------|
| 功能定位 | 完整推理过程 | 建立信任感 |
| 展示时机 | 实时流式 | 透明度最高 |
| 内容层级 | 业务信息 + 技术分层 | 不干扰 + 可选深入了解 |
| 收起状态 | 当前步骤 + 动态图标 | 简洁 + 有状态感 |
| 思考气泡 | 微蓝背景 + 斜体 + CPU | Signature Element |
| 实现方案 | 方案 B | 平衡设计自由度和工作量 |

---

## 九、验收标准

### 9.1 功能验收

- ✅ 默认收起状态显示当前步骤
- ✅ 点击展开显示完整推理过程
- ✅ 思考气泡显示 AI 推理（微蓝背景 + 斜体）
- ✅ 业务参数格式化（"正在搜索：光大证券"）
- ✅ 轮次分隔线清晰
- ✅ SSE 事件实时映射

### 9.2 设计验收

- ✅ 思考气泡使用 `$wolf-bg-ai-message`
- ✅ 遵循所有 Design Token
- ✅ 不显示技术参数名（"keyword ="）
- ✅ Signature Element 突出

### 9.3 测试验收

- ✅ 新组件覆盖率 ≥100%
- ✅ 所有测试用例通过
- ✅ 边界情况覆盖（错误、空状态、等待）
- ✅ **业务化验证测试已添加**（2026-06-22 补充）

### 9.4 错误处理验收（2026-06-22 补充修复）

- ✅ `getSuggestion` 函数已实现（需求文档 5.2）
- ✅ `waiting_for_user` 自动展开已实现（需求文档 5.3）
- ✅ `shouldAutoExpand` 状态管理已实现

### 9.5 Reduced Motion 验收（2026-06-22 补充修复）

- ✅ `ThinkingBubble.vue` 添加 `@media (prefers-reduced-motion)`
- ✅ `AgentExecutionLog.vue` 添加 `@media (prefers-reduced-motion)`
- ✅ 遵循 frontend-design skill 要求

---

## 十、相关文档

| 文档 | 路径 |
|------|------|
| 设计原则 | `CRM-Client/docs/DESIGN-PRINCIPLES.md` |
| 组件规范 | `CRM-Client/docs/COMPONENTS.md` |
| 测试规范 | `CRM-Client/docs/TESTING.md` |
| AI API 标准 | `CRM-Docs/standards/AI-API-STANDARD.md` |

---

**需求状态**：已批准并实施  
**实施状态**：组件已开发完成  
**文档创建日期**：2026-06-22

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| Design Review | `/plan-design-review` | UI/UX gaps | 1 | issues_open | score: 6/10 → 6/10, 4 decisions |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | issues_open | 4 issues, 0 critical gaps |

**VERDICT:** Design + Eng Review completed — 4 engineering issues recorded

**UNRESOLVED DECISIONS:** All 4 engineering issues resolved:
- D1: Split useAgentExecutionLog composable (SSE parser + state management)
- D2: Add suggestion field in handleToolResult (需求文档 5.2)
- D3: Create useAgentExecutionLog.test.ts for SSE event mapping
- D4: Add error state rendering test in AgentExecutionLog.test.ts

NO UNRESOLVED DECISIONS