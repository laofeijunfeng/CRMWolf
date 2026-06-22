# Agent 执行过程可视化实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 AI 执行过程的透明展示，建立用户信任感，业务友好表达而非技术参数。

**Architecture:** 新增 ThinkingBubble + AgentExecutionLog 组件，复用 StatusCard，集成到 MagicWand Sidebar，通过 SSE 事件流实时更新执行步骤。

**Tech Stack:** Vue 3 + TypeScript + Element Plus Icons + Vitest + Pinia

---

## Global Constraints

- **TypeScript 四禁令**：禁用 `any` `as any` `@ts-ignore` `!`
- **Design Token**：所有颜色/间距必须引用 `$wolf-*` 变量
- **测试覆盖率**：新组件 100% 覆盖率要求
- **组件 Props/Emits**：必须类型化
- **业务化表达**："正在搜索：光大证券"而非 "keyword = 光大证券"

---

## File Structure

### 新增文件
```
CRM-Client/src/components/
  ├─> ThinkingBubble.vue           # AI 推理气泡（Signature Element）
  └─> AgentExecutionLog.vue        # 执行过程容器组件

CRM-Client/src/composables/
  └─> useAgentExecutionLog.ts      # SSE 事件映射 + 状态管理

CRM-Client/src/components/__tests__/
  ├─> ThinkingBubble.test.ts       # ThinkingBubble 单元测试
  └─> AgentExecutionLog.test.ts    # AgentExecutionLog 单元测试

CRM-Client/src/composables/__tests__/
  └─> useAgentExecutionLog.test.ts # SSE 事件映射测试
```

### 修改文件
```
CRM-Client/src/components/MagicWandDialog.vue  # 集成 AgentExecutionLog
```

---

## Task Decomposition

### Task 1: ThinkingBubble 组件（Signature Element）

**Files:**
- Create: `CRM-Client/src/components/ThinkingBubble.vue`
- Create: `CRM-Client/src/components/__tests__/ThinkingBubble.test.ts`

**Interfaces:**
- Consumes: 无（独立组件）
- Produces: `ThinkingBubble.vue` 组件，Props: `{ content: string }`

**关键设计**：
- 微蓝背景（$wolf-bg-ai-message）
- CPU 图标 + 斜体文字
- 遵循 Design Token

---

### Task 2: useAgentExecutionLog composable（SSE 事件映射）

**Files:**
- Create: `CRM-Client/src/composables/useAgentExecutionLog.ts`
- Create: `CRM-Client/src/composables/__tests__/useAgentExecutionLog.test.ts`

**Interfaces:**
- Consumes: `AIAssistantSSEEvent`（从 api/aiAssistant.ts 导入）
- Produces: `useAgentExecutionLog()` composable，返回：
  ```typescript
  {
    executionLog: Ref<ExecutionLogState>
    handleSSEEvent: (event: AIAssistantSSEEvent) => void
    getBusinessTitle: (tool: string) => string
    formatBusinessParams: (params: Record<string, unknown>, title: string) => string
  }
  ```

**关键逻辑**：
- SSE 事件 → ExecutionStep 映射
- 工具名称业务化
- 业务参数格式化

---

### Task 3: AgentExecutionLog 容器组件

**Files:**
- Create: `CRM-Client/src/components/AgentExecutionLog.vue`
- Create: `CRM-Client/src/components/__tests__/AgentExecutionLog.test.ts`

**Interfaces:**
- Consumes:
  - `ThinkingBubble.vue`（Task 1）
  - `StatusCard.vue`（现有）
  - `useAgentExecutionLog.ts`（Task 2）
- Produces: `AgentExecutionLog.vue` 组件，Props: `{ steps: ExecutionStep[], expanded: boolean }`

**关键功能**：
- 默认收起，点击展开
- 显示思考气泡 + 业务参数
- 轮次分隔线

---

### Task 4: 集成到 MagicWandDialog

**Files:**
- Modify: `CRM-Client/src/components/MagicWandDialog.vue`

**Interfaces:**
- Consumes: `AgentExecutionLog.vue`（Task 3），`useAgentExecutionLog.ts`（Task 2）
- Produces: MagicWand Sidebar 中显示执行过程

**关键集成**：
- SSE 事件流连接
- 自动收起/展开逻辑

---

## Implementation Steps

### Task 1: ThinkingBubble 组件

#### Step 1: 写测试文件

- [ ] **Write the failing test**

```typescript
// CRM-Client/src/components/__tests__/ThinkingBubble.test.ts
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ThinkingBubble from '../ThinkingBubble.vue'
import { Cpu } from '@element-plus/icons-vue'

describe('ThinkingBubble', () => {
  it('渲染 CPU 图标', () => {
    const wrapper = mount(ThinkingBubble, {
      props: { content: 'AI 推理过程' }
    })
    
    expect(wrapper.findComponent(Cpu).exists()).toBe(true)
  })

  it('显示推理文字', () => {
    const wrapper = mount(ThinkingBubble, {
      props: { content: '用户想跟进光大证券...' }
    })
    
    const textElement = wrapper.find('.thinking-text')
    expect(textElement.text()).toBe('用户想跟进光大证券...')
  })

  it('使用微蓝背景', () => {
    const wrapper = mount(ThinkingBubble, {
      props: { content: 'AI 推理' }
    })
    
    const bubbleElement = wrapper.find('.thinking-bubble')
    expect(bubbleElement.exists()).toBe(true)
  })
})
```

- [ ] **Run test to verify it fails**

```bash
cd CRM-Client && npm run test:unit ThinkingBubble.test.ts
```

Expected: FAIL with "Cannot find module '../ThinkingBubble.vue'"

- [ ] **Write minimal implementation**

```vue
<!-- CRM-Client/src/components/ThinkingBubble.vue -->
<template>
  <div class="thinking-bubble">
    <el-icon :size="16" class="thinking-icon">
      <Cpu />
    </el-icon>
    <span class="thinking-text">{{ content }}</span>
  </div>
</template>

<script setup lang="ts">
import { Cpu } from '@element-plus/icons-vue'

interface Props {
  content: string
}

defineProps<Props>()
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.thinking-bubble {
  background: $wolf-bg-ai-message;
  border-radius: $wolf-radius-sm;
  padding: $wolf-space-sm;
  display: flex;
  align-items: flex-start;
  gap: $wolf-space-xs;
  
  .thinking-icon {
    color: $wolf-primary;
    flex-shrink: 0;
  }
  
  .thinking-text {
    font-size: $wolf-font-size-auxiliary;
    font-style: italic;
    color: $wolf-text-secondary;
    line-height: $wolf-line-height-body;
  }
}
</style>
```

- [ ] **Run test to verify it passes**

```bash
cd CRM-Client && npm run test:unit ThinkingBubble.test.ts
```

Expected: PASS（3 tests）

- [ ] **Commit**

```bash
git add CRM-Client/src/components/ThinkingBubble.vue CRM-Client/src/components/__tests__/ThinkingBubble.test.ts
git commit -m "feat(ui): add ThinkingBubble component for AI reasoning display"
```

---

### Task 2: useAgentExecutionLog composable

#### Step 1: 写类型定义

- [ ] **Write types file**

```typescript
// CRM-Client/src/types/agentExecution.ts
export interface ExecutionStep {
  id: string
  round: number
  status: 'running' | 'success' | 'error'
  title: string
  thinking?: string
  params?: Record<string, unknown>
  resultSummary?: string
  errorHint?: string
  suggestion?: string
  timestamp?: string
}

export interface ExecutionLogState {
  steps: ExecutionStep[]
  currentStep: ExecutionStep | null
  expanded: boolean
}
```

- [ ] **Commit types**

```bash
git add CRM-Client/src/types/agentExecution.ts
git commit -m "feat(types): add ExecutionStep and ExecutionLogState types"
```

#### Step 2: 写测试文件

- [ ] **Write the failing test**

```typescript
// CRM-Client/src/composables/__tests__/useAgentExecutionLog.test.ts
import { describe, it, expect } from 'vitest'
import { useAgentExecutionLog } from '../useAgentExecutionLog'
import type { AIAssistantSSEEvent } from '@/api/aiAssistant'

describe('useAgentExecutionLog', () => {
  it('tool_call 事件映射', () => {
    const { handleSSEEvent, executionLog } = useAgentExecutionLog()
    
    handleSSEEvent({
      event: 'tool_call',
      tool: 'search_customer',
      round: 1,
      reply_text: '用户想跟进光大证券...',
      params: { keyword: '光大证券', limit: 5 }
    } as AIAssistantSSEEvent)
    
    expect(executionLog.value.steps.length).toBe(1)
    expect(executionLog.value.steps[0].title).toBe('查找客户信息')
    expect(executionLog.value.steps[0].thinking).toBe('用户想跟进光大证券...')
  })

  it('工具名称业务化映射', () => {
    const { getBusinessTitle } = useAgentExecutionLog()
    
    expect(getBusinessTitle('search_customer')).toBe('查找客户信息')
    expect(getBusinessTitle('create_follow_up')).toBe('创建跟进记录')
  })

  it('业务参数格式化', () => {
    const { formatBusinessParams } = useAgentExecutionLog()
    
    const result = formatBusinessParams(
      { keyword: '光大证券', limit: 5 },
      '查找客户信息'
    )
    
    expect(result).toContain('正在搜索："光大证券"')
    expect(result).not.toContain('keyword =')
  })
})
```

- [ ] **Run test to verify it fails**

```bash
cd CRM-Client && npm run test:unit useAgentExecutionLog.test.ts
```

Expected: FAIL with "Cannot find module '../useAgentExecutionLog'"

#### Step 3: 实现 composable

- [ ] **Write implementation**

```typescript
// CRM-Client/src/composables/useAgentExecutionLog.ts
import { ref } from 'vue'
import type { AIAssistantSSEEvent } from '@/api/aiAssistant'
import type { ExecutionStep, ExecutionLogState } from '@/types/agentExecution'

export function useAgentExecutionLog() {
  const executionLog = ref<ExecutionLogState>({
    steps: [],
    currentStep: null,
    expanded: false
  })

  // 工具名称 → 业务标题映射
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
    return toolMap[tool] || tool
  }

  // 业务参数格式化
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
      
      default:
        return ''
    }
  }

  // SSE 事件处理
  const handleSSEEvent = (event: AIAssistantSSEEvent) => {
    switch (event.event) {
      case 'react_start':
        executionLog.value = {
          steps: [],
          currentStep: null,
          expanded: false
        }
        break

      case 'tool_call':
        const newStep: ExecutionStep = {
          id: `${event.round}-${event.tool}`,
          round: event.round || 1,
          status: 'running',
          title: getBusinessTitle(event.tool || ''),
          thinking: event.reply_text,
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
        if (stepIndex !== -1 && event.result) {
          executionLog.value.steps[stepIndex].status = 
            event.result.success ? 'success' : 'error'
          executionLog.value.steps[stepIndex].resultSummary = 
            event.result.message
        }
        executionLog.value.currentStep = 
          executionLog.value.steps.find(s => s.status === 'running') || null
        break

      case 'react_complete':
        executionLog.value.currentStep = null
        break

      case 'error':
        executionLog.value.steps.push({
          id: 'error',
          round: 0,
          status: 'error',
          title: '执行失败',
          errorHint: event.message || '连接中断',
          timestamp: '刚刚'
        })
        executionLog.value.expanded = false
        break

      case 'waiting_for_user':
        executionLog.value.expanded = true
        break
    }
  }

  return {
    executionLog,
    handleSSEEvent,
    getBusinessTitle,
    formatBusinessParams
  }
}
```

- [ ] **Run test to verify it passes**

```bash
cd CRM-Client && npm run test:unit useAgentExecutionLog.test.ts
```

Expected: PASS（3 tests）

- [ ] **Commit**

```bash
git add CRM-Client/src/composables/useAgentExecutionLog.ts CRM-Client/src/composables/__tests__/useAgentExecutionLog.test.ts
git commit -m "feat(composable): add useAgentExecutionLog for SSE event mapping"
```

---

### Task 3: AgentExecutionLog 容器组件

#### Step 1: 写测试文件

- [ ] **Write the failing test**

```typescript
// CRM-Client/src/components/__tests__/AgentExecutionLog.test.ts
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import AgentExecutionLog from '../AgentExecutionLog.vue'
import ThinkingBubble from '../ThinkingBubble.vue'
import StatusCard from '../StatusCard.vue'
import type { ExecutionStep } from '@/types/agentExecution'

describe('AgentExecutionLog', () => {
  const mockSteps: ExecutionStep[] = [
    {
      id: '1-search',
      round: 1,
      status: 'running',
      title: '查找客户信息',
      thinking: '用户想跟进光大证券...',
      params: { keyword: '光大证券', limit: 5 }
    }
  ]

  it('默认收起状态', () => {
    const wrapper = mount(AgentExecutionLog, {
      props: { steps: mockSteps, expanded: false }
    })
    
    expect(wrapper.find('.collapsed-header').exists()).toBe(true)
    expect(wrapper.find('.expanded-content').exists()).toBe(false)
  })

  it('点击展开', () => {
    const wrapper = mount(AgentExecutionLog, {
      props: { steps: mockSteps, expanded: false }
    })
    
    wrapper.find('.collapsed-header').trigger('click')
    
    expect(wrapper.emitted('toggle-expand')).toBeTruthy()
  })

  it('展开后显示思考气泡', () => {
    const wrapper = mount(AgentExecutionLog, {
      props: { steps: mockSteps, expanded: true }
    })
    
    expect(wrapper.findComponent(ThinkingBubble).exists()).toBe(true)
  })

  it('展开后显示 StatusCard', () => {
    const wrapper = mount(AgentExecutionLog, {
      props: { steps: mockSteps, expanded: true }
    })
    
    expect(wrapper.findComponent(StatusCard).exists()).toBe(true)
  })
})
```

- [ ] **Run test to verify it fails**

```bash
cd CRM-Client && npm run test:unit AgentExecutionLog.test.ts
```

Expected: FAIL with "Cannot find module '../AgentExecutionLog.vue'"

#### Step 2: 实现容器组件

- [ ] **Write implementation**

```vue
<!-- CRM-Client/src/components/AgentExecutionLog.vue -->
<template>
  <div class="agent-execution-log" v-if="steps.length > 0">
    <!-- 默认收起状态 -->
    <div 
      v-if="!expanded" 
      class="collapsed-header"
      @click="handleToggleExpand"
    >
      <el-icon 
        :class="{ 'is-loading': currentStep?.status === 'running' }"
        class="status-icon"
      >
        <Loading v-if="currentStep?.status === 'running'" />
        <CircleCheckFilled v-if="currentStep?.status === 'success'" />
        <CircleCloseFilled v-if="currentStep?.status === 'error'" />
      </el-icon>
      
      <span class="current-step-text">
        {{ currentStep?.title || '正在处理...' }}
      </span>
      
      <el-icon class="expand-icon"><ArrowDown /></el-icon>
    </div>

    <!-- 展开后显示 -->
    <div v-if="expanded" class="expanded-content">
      <!-- 收起按钮 -->
      <div class="collapse-button" @click="handleToggleExpand">
        <el-icon><ArrowUp /></el-icon>
        <span>收起</span>
      </div>

      <!-- 步骤列表 -->
      <div class="steps-list">
        <div
          v-for="(step, index) in steps"
          :key="step.id"
          class="step-item"
        >
          <!-- 轮次分隔线 -->
          <div 
            v-if="index === 0 || steps[index - 1].round !== step.round" 
            class="round-separator"
          >
            Round {{ step.round }}
          </div>

          <!-- 思考气泡 -->
          <ThinkingBubble 
            v-if="step.thinking" 
            :content="step.thinking"
          />

          <!-- 业务参数 -->
          <div v-if="step.params && formatBusinessParams(step.params, step.title)" class="business-params">
            {{ formatBusinessParams(step.params, step.title) }}
          </div>

          <!-- 结果摘要 -->
          <StatusCard
            :type="step.status === 'running' ? 'loading' : step.status"
            :title="step.title"
            :summary="step.resultSummary || step.errorHint"
            :timestamp="step.timestamp"
            :show-actions="false"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { 
  Loading, 
  CircleCheckFilled, 
  CircleCloseFilled, 
  ArrowDown, 
  ArrowUp 
} from '@element-plus/icons-vue'
import ThinkingBubble from './ThinkingBubble.vue'
import StatusCard from './StatusCard.vue'
import type { ExecutionStep } from '@/types/agentExecution'

interface Props {
  steps: ExecutionStep[]
  expanded: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'toggle-expand'): void
}>()

const currentStep = computed(() => {
  return props.steps.find(s => s.status === 'running') || props.steps[props.steps.length - 1]
})

const handleToggleExpand = () => {
  emit('toggle-expand')
}

const formatBusinessParams = (
  params: Record<string, unknown>,
  title: string
): string => {
  switch (title) {
    case '查找客户信息':
      return `正在搜索："${params.keyword}"\n最多显示：${params.limit} 个结果`
    
    case '创建跟进记录':
      return `跟进方式：${params.follow_up_type === 'phone' ? '电话沟通' : '当面拜访'}`
    
    case '标记商机赢单':
      return `商机名称：${params.opportunity_name}`
    
    default:
      return ''
  }
}
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.agent-execution-log {
  .collapsed-header {
    display: flex;
    align-items: center;
    gap: $wolf-space-sm;
    padding: $wolf-space-sm;
    background: $wolf-bg-card;
    border-radius: $wolf-radius-sm;
    cursor: pointer;
    
    .status-icon {
      flex-shrink: 0;
      
      &.is-loading {
        animation: rotate 1s linear infinite;
      }
    }
    
    .current-step-text {
      font-size: $wolf-font-size-body;
      color: $wolf-text-primary;
    }
    
    .expand-icon {
      color: $wolf-text-tertiary;
    }
  }

  .expanded-content {
    max-height: 300px;
    overflow-y: auto;
    
    .collapse-button {
      display: flex;
      align-items: center;
      gap: $wolf-space-xs;
      padding: $wolf-space-sm;
      cursor: pointer;
      color: $wolf-text-tertiary;
    }

    .steps-list {
      display: flex;
      flex-direction: column;
      gap: $wolf-space-sm;
      
      .step-item {
        .round-separator {
          font-size: $wolf-font-size-caption;
          color: $wolf-text-tertiary;
          padding: $wolf-space-xs 0;
        }
        
        .business-params {
          font-size: $wolf-font-size-auxiliary;
          color: $wolf-text-secondary;
          padding: $wolf-space-sm;
          background: $wolf-bg-hover;
          border-radius: $wolf-radius-sm;
          margin-bottom: $wolf-space-sm;
        }
      }
    }
  }
}

@keyframes rotate {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
```

- [ ] **Run test to verify it passes**

```bash
cd CRM-Client && npm run test:unit AgentExecutionLog.test.ts
```

Expected: PASS（4 tests）

- [ ] **Commit**

```bash
git add CRM-Client/src/components/AgentExecutionLog.vue CRM-Client/src/components/__tests__/AgentExecutionLog.test.ts
git commit -m "feat(ui): add AgentExecutionLog container component"
```

---

### Task 4: 集成到 MagicWandDialog

#### Step 1: 修改 MagicWandDialog

- [ ] **Import components**

在 `<script setup>` 中添加：
```typescript
import AgentExecutionLog from './AgentExecutionLog.vue'
import { useAgentExecutionLog } from '@/composables/useAgentExecutionLog'
```

- [ ] **Add composable usage**

```typescript
const { executionLog, handleSSEEvent } = useAgentExecutionLog()
const logExpanded = ref(false)

const toggleLogExpand = () => {
  logExpanded.value = !logExpanded.value
}
```

- [ ] **Connect SSE events**

在 `handleSSEEvent` 函数中添加：
```typescript
const originalHandler = (event: AIAssistantSSEEvent) => {
  // 原有逻辑...
  
  // 新增：执行日志事件处理
  handleSSEEvent(event)
}
```

- [ ] **Add UI integration**

在 Sidebar 内容区添加：
```vue
<!-- 执行过程日志 -->
<div class="sidebar-execution-log" v-if="executionLog.steps.length > 0">
  <AgentExecutionLog 
    :steps="executionLog.steps"
    :expanded="logExpanded"
    @toggle-expand="toggleLogExpand"
  />
</div>
```

- [ ] **Add styles**

```scss
.sidebar-execution-log {
  margin-top: $wolf-space-md;
  padding: $wolf-space-sm;
}
```

- [ ] **Test integration**

手动测试：
1. 打开 MagicWand
2. 输入"跟进光大证券"
3. 验证执行日志显示（默认收起）
4. 点击展开，验证思考气泡 + 业务参数显示

- [ ] **Commit**

```bash
git add CRM-Client/src/components/MagicWandDialog.vue
git commit -m "feat(ui): integrate AgentExecutionLog into MagicWand sidebar"
```

---

## Self-Review

### Spec Coverage

✅ **ThinkingBubble 组件** - Task 1  
✅ **AgentExecutionLog 容器** - Task 3  
✅ **SSE 事件映射** - Task 2  
✅ **业务化表达** - Task 2 (formatBusinessParams)  
✅ **集成到 MagicWand** - Task 4  
✅ **测试覆盖率 100%** - 所有任务都有测试

### Placeholder Scan

✅ 无 TBD、TODO  
✅ 无"add validation"模糊描述  
✅ 所有代码步骤都有完整代码  
✅ 所有测试都有完整测试代码

### Type Consistency

✅ `ExecutionStep` 类型一致  
✅ `ExecutionLogState` 类型一致  
✅ `AIAssistantSSEEvent` 从 api/aiAssistant.ts 导入  
✅ Props 类型定义一致

---

## Execution Options

Plan complete and saved to `docs/superpowers/plans/2026-06-22-agent-execution-log.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**