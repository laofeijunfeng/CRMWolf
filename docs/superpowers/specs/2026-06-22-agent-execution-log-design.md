# Agent 执行过程可视化设计文档

**设计日期**：2026-06-22  
**设计者**：Claude Code (Frontend Design + Brainstorming Skill)  
**版本**：v1.0

---

## 一、设计目标

### 1.1 核心目标

**透明展示 AI 执行过程，建立信任感**

- 让销售人员理解 AI 在做什么、为什么这么做
- 业务友好表达，避免技术化术语
- 实时流式显示，增强透明感
- 克制设计，不干扰主对话区域

### 1.2 用户画像

- **主要用户**：销售人员、客户经理
- **关注点**：AI 在做什么？为什么这么做？做得怎么样？
- **不关心**：技术工具名称、技术参数格式、数据结构

### 1.3 成功标准

1. ✅ 用户能理解 AI 推理过程（思考气泡突出）
2. ✅ 用户能看到业务信息（"正在搜索：光大证券"，而非 "keyword ="）
3. ✅ 用户不被干扰（默认收起，点击展开）
4. ✅ 用户建立信任感（透明展示执行过程）

---

## 二、整体架构

### 2.1 组件结构

```
MagicWandDialog.vue（现有）
  └─> AgentExecutionLog.vue（新增，容器组件）
       ├─> CollapsedHeader（收起状态）
       │    ├─> <Loading /> 图标（旋转动画）
       │    ├─> 当前步骤文本（业务化）
       │    └─> <ArrowDown /> 图标（点击展开）
       │
       └─> ExpandedContent（展开状态）
            ├─> ThinkingBubble.vue（新增）
            │    ├─> CPU 图标
            │    └─> AI 推理文字（斜体）
            ├─> StatusCard.vue（复用）
            │    ├─> 状态图标（SuccessFilled/CircleCloseFilled/Loading）
            │    ├─> 步骤标题（业务化）
            │    └─> 结果摘要
            └─> BusinessParams（业务参数格式化）
                 └─> 业务友好表达（"正在搜索："而非 "keyword ="）
```

### 2.2 文件结构

```
CRM-Client/src/components/
  ├─> ThinkingBubble.vue（新增，30行）
  ├─> AgentExecutionLog.vue（新增，80行）
  ├─> StatusCard.vue（复用，无需修改）
  └─> MagicWandDialog.vue（修改，集成 AgentExecutionLog）

CRM-Client/src/composables/
  └─> useAgentExecutionLog.ts（新增，SSE 事件映射逻辑，40行）

CRM-Client/src/components/__tests__/
  ├─> ThinkingBubble.test.ts（新增，50行）
  └─> AgentExecutionLog.test.ts（新增，100行）

CRM-Client/src/composables/__tests__/
  └─> useAgentExecutionLog.test.ts（新增，50行）
```

### 2.3 数据流

```
SSE 事件流 → useAgentExecutionLog.ts → 状态管理
  ├─> react_start → 初始化日志
  ├─> round_start → 显示轮次分隔
  ├─> tool_call → 显示思考气泡 + 业务参数
  ├─> tool_result → 显示结果摘要
  ├─> react_complete → 显示完成状态
  ├─> waiting_for_user → 自动展开（需要用户关注）
  └─> error → 显示错误提示 + 自动收起
```

---

## 三、组件设计细节

### 3.1 ThinkingBubble 组件（Signature Element）

**定位**：AI 推理过程的独特标识，区别于普通步骤。

**Props 定义**：
```typescript
interface ThinkingBubbleProps {
  content: string  // AI 推理过程文本
}
```

**视觉设计**：
- **背景色**：$wolf-bg-ai-message（#F0F4F8，微蓝）- 暗示智能
- **图标**：CPU 图标（Element Plus Icons `<Cpu />`）- 品牌一致
- **字体**：斜体（font-style: italic）- 传达"思考过程"而非"事实"
- **字号**：$wolf-font-size-auxiliary（13px）- 辅助信息层级
- **字色**：$wolf-text-secondary（#3A3A3A）- 次要信息
- **圆角**：$wolf-radius-sm（4px）- 克制
- **内边距**：$wolf-space-sm（8px）- 适中

**样式实现**：
```scss
.thinking-bubble {
  background: $wolf-bg-ai-message;  // 微蓝背景
  border-radius: $wolf-radius-sm;   // 4px
  padding: $wolf-space-sm;          // 8px
  display: flex;
  align-items: flex-start;
  gap: $wolf-space-xs;              // 4px
  
  .thinking-icon {
    color: $wolf-primary;           // 品牌蓝
    flex-shrink: 0;
  }
  
  .thinking-text {
    font-size: $wolf-font-size-auxiliary;  // 13px
    font-style: italic;                      // 斜体（关键）
    color: $wolf-text-secondary;            // #3A3A3A
    line-height: $wolf-line-height-body;    // 1.5
  }
}
```

**使用示例**：
```vue
<ThinkingBubble content="用户想跟进光大证券，需要先找到对应的客户记录..." />
```

---

### 3.2 AgentExecutionLog 容器组件

**定位**：管理收起/展开状态，展示完整执行过程。

**Props 定义**：
```typescript
interface AgentExecutionLogProps {
  steps: ExecutionStep[]      // 执行步骤数组
  currentStep?: ExecutionStep // 当前进行中的步骤
  expanded: boolean           // 展开/收起状态
}

interface ExecutionStep {
  id: string
  round: number
  status: 'running' | 'success' | 'error'
  title: string               // 业务标题（"查找客户信息"）
  thinking?: string           // AI 推理过程
  params?: Record<string, unknown>
  resultSummary?: string      // 结果摘要（"找到 5 个客户"）
  errorHint?: string          // 错误提示（"未找到匹配客户"）
  suggestion?: string         // 解决建议（"建议：请提供更精确的客户名称"）
  timestamp?: string          // 时间戳（"刚刚"）
}
```

#### 3.2.1 收起状态设计

**默认显示**：
```
┌─────────────────────────────────┐
│ [⟳] 正在搜索客户...             │ ← 当前步骤 + 旋转图标
│ [点击展开查看详细过程]           │ ← 提示可展开
└─────────────────────────────────┘
```

**实现**：
```vue
<div class="collapsed-header" @click="toggleExpand">
  <el-icon :class="{ 'is-loading': currentStep?.status === 'running' }">
    <Loading v-if="currentStep?.status === 'running'" />
    <CircleCheckFilled v-if="currentStep?.status === 'success'" />
    <CircleCloseFilled v-if="currentStep?.status === 'error'" />
  </el-icon>
  
  <span class="current-step-text">
    {{ currentStep?.title || '正在处理...' }}
  </span>
  
  <el-icon class="expand-icon"><ArrowDown /></el-icon>
</div>
```

#### 3.2.2 展开状态设计

**完整显示**：
```
┌─────────────────────────────────┐
│ [收起] ▲                        │
│                                 │
│ Round 1                         │ ← 轮次分隔
│ ┌───────────────────────┐       │
│ │ 💭 用户想跟进光大证券，│     │ ← 思考气泡
│ │      需要先找到客户...  │     │
│ └───────────────────────┘       │
│                                 │
│ 正在搜索："光大证券"             │ ← 业务参数
│                                 │
│ ✓ 找到 5 个客户                  │ ← 结果摘要
│                                 │
│ Round 2                         │
│ ┌───────────────────────┐       │
│ │ 💭 已找到客户，现在    │     │
│ │      创建跟进记录...    │     │
│ └───────────────────────┘       │
│                                 │
│ 正在创建跟进记录                  │ ← 业务参数
│ 客户：光大证券                   │
│                                 │
│ ✓ 已创建跟进记录                 │ ← 结果摘要
└─────────────────────────────────┘
```

#### 3.2.3 业务参数格式化（关键：业务友好）

**核心逻辑**：
```typescript
const formatBusinessParams = (
  params: Record<string, unknown>, 
  title: string
): string => {
  switch (title) {
    case '查找客户信息':
      return `正在搜索："${params.keyword}"\n最多显示：${params.limit} 个结果`
    
    case '创建跟进记录':
      return `跟进方式：${params.follow_up_type === 'phone' ? '电话沟通' : '当面拜访'}\n客户：${params.customer_name}`
    
    case '标记商机赢单':
      return `商机名称：${params.opportunity_name}\n标记状态：赢单`
    
    case '更新客户资料':
      return `客户：${params.customer_name}\n更新字段：${params.fields}`
    
    default:
      return ''  // 不显示参数（避免技术化）
  }
}
```

**关键设计决策**：
- ✅ "正在搜索："而非 "keyword ="
- ✅ "最多显示：5 个结果"而非 "limit = 5"
- ✅ 默认不显示参数（兜底）- 避免技术化表达

---

### 3.3 SSE 事件映射逻辑

**工具名称 → 业务标题映射**：
```typescript
const getBusinessTitle = (tool: string): string => {
  const toolMap: Record<string, string> = {
    'search_customer': '查找客户信息',
    'create_follow_up': '创建跟进记录',
    'win_opportunity': '标记商机赢单',
    'lose_opportunity': '标记商机输单',
    'create_contract': '创建合同',
    'update_customer': '更新客户资料',
    'get_entity_context': '获取上下文信息'
  }
  
  return toolMap[tool] || tool  // 兜底：返回原始名称
}
```

**SSE 事件 → ExecutionStep 映射**：
```typescript
const handleSSEEvent = (event: AIAssistantSSEEvent) => {
  switch (event.event) {
    case 'react_start':
      executionLog.value = { steps: [], currentStep: null, expanded: false }
      break

    case 'tool_call':
      const newStep: ExecutionStep = {
        id: `${event.round}-${event.tool}`,
        round: event.round || 1,
        status: 'running',
        title: getBusinessTitle(event.tool),  // 业务化标题
        thinking: event.reply_text,  // AI 推理过程
        params: event.params,
        timestamp: '刚刚'
      }
      executionLog.value.steps.push(newStep)
      executionLog.value.currentStep = newStep
      break

    case 'tool_result':
      const stepIndex = executionLog.value.steps.findIndex(
        s => s.id === `${event.round}-${event.tool}`
      )
      
      if (stepIndex !== -1) {
        executionLog.value.steps[stepIndex] = {
          ...executionLog.value.steps[stepIndex],
          status: event.result?.success ? 'success' : 'error',
          resultSummary: event.result?.message,
          errorHint: event.result?.success ? undefined : '执行失败'
        }
      }
      
      executionLog.value.currentStep = 
        executionLog.value.steps.find(s => s.status === 'running')
      break

    case 'react_complete':
      executionLog.value.currentStep = null
      break
  }
}
```

---

## 四、错误处理与边界情况

### 4.1 SSE 连接错误

**处理逻辑**：
```typescript
case 'error':
  const errorStep: ExecutionStep = {
    id: 'error-connection',
    round: 0,
    status: 'error',
    title: '执行失败',
    errorHint: event.message || '连接中断，请重试',
    timestamp: '刚刚'
  }
  
  executionLog.value.steps.push(errorStep)
  executionLog.value.currentStep = null
  executionLog.value.expanded = false  // 自动收起
```

### 4.2 工具执行失败

**错误提示 + 解决建议映射**：
```typescript
const getSuggestion = (tool: string, errorMessage: string): string => {
  switch (tool) {
    case 'search_customer':
      if (errorMessage.includes('未找到')) {
        return '建议：请提供更精确的客户名称'
      }
      break
    
    case 'create_follow_up':
      if (errorMessage.includes('客户不存在')) {
        return '建议：请先创建客户记录'
      }
      break
    
    case 'win_opportunity':
      if (errorMessage.includes('商机不存在')) {
        return '建议：请先创建商机'
      }
      break
    
    default:
      return '建议：请检查输入信息是否正确'
  }
}
```

**关键设计**：
- ✅ 业务友好提示（"建议：请提供更精确的客户名称"）
- ✅ 不显示技术错误（"NotFoundError"）

### 4.3 最大轮数限制

```typescript
case 'max_rounds_reached':
  executionLog.value.steps.push({
    id: 'max-rounds',
    round: event.round || 10,
    status: 'success',  // 部分完成，非失败
    title: '执行完成（部分）',
    resultSummary: `已完成 ${event.round} 轮处理，达到最大轮数限制`,
    timestamp: '刚刚'
  })
```

### 4.4 空状态处理

```typescript
const showExecutionLog = computed(() => {
  return executionLog.value.steps.length > 0
})

<AgentExecutionLog v-if="showExecutionLog" :steps="executionLog.steps" />
```

### 4.5 Human-in-the-Loop

```typescript
case 'waiting_for_user':
  executionLog.value.steps.push({
    id: 'waiting-user',
    round: event.round || 1,
    status: 'running',
    title: '等待您的回复',
    thinking: event.question,
    resultSummary: event.context_hint
  })
  
  executionLog.value.expanded = true  // 自动展开（需要用户关注）
```

---

## 五、测试策略

### 5.1 覆盖率要求

遵循 CRMWolf 测试规范：
- **新组件**：100% 覆盖率
- **测试文件**：每个组件配 `.test.ts` 文件

### 5.2 ThinkingBubble 测试

**测试用例**：
```typescript
describe('ThinkingBubble', () => {
  it('渲染 CPU 图标')
  it('显示斜体文字')
  it('使用微蓝背景')
  it('遵循 Design Token')
})
```

### 5.3 AgentExecutionLog 测试

**测试用例**：
```typescript
describe('AgentExecutionLog', () => {
  it('默认收起状态')
  it('点击展开')
  it('显示思考气泡')
  it('业务参数格式化')
  it('轮次分隔线')
  it('复用 StatusCard')
})
```

### 5.4 SSE 事件映射测试

**测试用例**：
```typescript
describe('useAgentExecutionLog', () => {
  it('tool_call 事件映射')
  it('tool_result 事件更新状态')
  it('工具名称业务化映射')
})
```

### 5.5 边界情况测试

**测试用例**：
```typescript
describe('边界情况', () => {
  it('SSE 连接错误')
  it('空状态不显示')
  it('等待用户回复自动展开')
})
```

---

## 六、设计原则遵循

### 6.1 克制原则

- ✅ 默认收起，不干扰主对话区域
- ✅ 新增最小必要组件（ThinkingBubble + AgentExecutionLog）
- ✅ 复用现有组件（StatusCard）
- ✅ 遵循 Design Token（$wolf-*）

### 6.2 业务友好原则

- ✅ 业务化表达（"正在搜索："而非 "keyword ="）
- ✅ 错误提示 + 解决建议（业务语言）
- ✅ 工具名称映射（业务标题）

### 6.3 透明展示原则

- ✅ 实时流式显示（用户看到"正在做..."）
- ✅ 思考气泡突出（微蓝背景 + 斜体）
- ✅ 完整推理过程（不隐藏中间环节）

### 6.4 品牌一致性原则

- ✅ CPU 图标（MagicWand 已使用）
- ✅ 微蓝背景（$wolf-bg-ai-message，暗示智能）
- ✅ StatusCard 组件（系统标准）

---

## 七、开发工作量估算

| 组件/文件 | 代码行数 | 开发时间 |
|---------|---------|---------|
| ThinkingBubble.vue | 30 行 | 30 分钟 |
| AgentExecutionLog.vue | 80 行 | 1 小时 |
| useAgentExecutionLog.ts | 40 行 | 40 分钟 |
| ThinkingBubble.test.ts | 50 行 | 30 分钟 |
| AgentExecutionLog.test.ts | 100 行 | 1 小时 |
| useAgentExecutionLog.test.ts | 50 行 | 30 分钟 |
| MagicWandDialog.vue（集成） | 20 行 | 20 分钟 |
| **总计** | **370 行** | **约 4 小时** |

---

## 八、技术实现约束

### 8.1 TypeScript 规范

- ✅ 禁用 `any` `as any` `@ts-ignore` `!`
- ✅ Props 必须类型化（`interface ThinkingBubbleProps`）
- ✅ 从 schemas/ 导入类型

### 8.2 Vue 组件规范

- ✅ Props 必须类型化（`Object as PropType<T>`）
- ✅ Emits 必须类型化（`defineEmits<{ ... }>()`）
- ✅ 禁止 any 类型

### 8.3 Design Token 规范

- ✅ 所有颜色引用 `$wolf-*` 变量
- ✅ 禁止硬编码颜色值
- ✅ 禁止魔数间距（使用 `$wolf-space-*`）

### 8.4 测试规范

- ✅ 新组件必须有 `.test.ts` 文件
- ✅ 覆盖率要求：100%
- ✅ Mock 数据必须类型化

---

## 九、后续优化方向

### 9.1 可选增强功能（YAGNI - 暂不实现）

- ❌ 用户自定义层级（选择展示哪些信息）- 过度设计
- ❌ 导出执行过程为 PDF - 无业务需求
- ❌ 实时干预 AI 执行 - 交互复杂度增加
- ❌ 执行过程回放 - 存储成本增加

### 9.2 未来可能扩展

- ⚠️ 技术细节展示（L2 层级）- 可选展开
- ⚠️ 执行过程搜索 - 可能有需求
- ⚠️ 执行过程统计（耗时分析）- 可能有需求

---

## 十、设计文档版本历史

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| v1.0 | 2026-06-22 | 初版设计文档（Brainstorming 流程完成） |

---

**文档状态**：已完成，等待用户审查  
**下一步**：用户审查后，调用 writing-plans skill 编写实现计划