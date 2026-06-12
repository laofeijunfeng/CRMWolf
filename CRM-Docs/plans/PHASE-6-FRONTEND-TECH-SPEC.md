---
status: active
created: 2026-06-09
updated: 2026-06-09
related_requirements: ../requirements/AI-TOOL-ENHANCEMENT-REQUIREMENTS.md
related_pr: -
---

# Phase 6：前端依次确认 UI 技术说明

> 版本：1.0 | 创建日期：2026-06-09 | 状态：待实施
> 配套计划：[AI-TOOL-ENHANCEMENT-PLAN.md](./AI-TOOL-ENHANCEMENT-PLAN.md)

---

## 一、改造概览

### 1.1 目标

前端支持多工具依次确认、ReAct 多轮展示、实体歧义消解 UI。

### 1.2 涉及组件

| 组件 | 改动类型 | 说明 |
|------|----------|------|
| `MagicWandDialog.vue` | **重构** | 支持多工具依次确认、多轮 ReAct 展示 |
| `ReactProgress.vue` | **新增** | 展示 ReAct 多轮进度 |
| `EntitySelectDialog.vue` | **新增** | 实体歧义选择界面 |
| `DynamicParamForm.vue` | **微调** | 支持单工具模式复用 |
| `aiAssistant.ts` | **扩展** | 新增 SSE 事件类型 + continue_react 接口 |

### 1.3 新增 SSE 事件类型

| 事件 | 触发场景 | 前端处理 |
|------|----------|----------|
| `parsed_multi` | AI 返回多个工具 | 依次展示确认弹窗 |
| `disambiguation_required` | 实体歧义（多商机等） | 展示选择界面 |
| `awaiting_confirmation` | ReAct 等待确认 | 暂停等待用户操作 |
| `round_completed` | 单轮执行完成 | 显示结果，等待下一轮 |
| `max_rounds_reached` | 达到最大轮数 | 显示完成信息 |

---

## 二、SSE 事件结构详解

### 2.1 `parsed_multi` 事件

```typescript
interface ParsedMultiEvent {
  event: 'parsed_multi'
  round: number                    // 当前轮数（ReAct 模式）
  tool_calls: ToolCall[]           // 工具调用列表
  reply_text: string               // AI 总体描述
  previous_results?: ExecutedResult[]  // 前几轮执行结果
}

interface ToolCall {
  tool: string                     // 工具名
  params: Record<string, unknown>  // 参数
  param_definitions?: Record<string, ParamDefinition>  // 参数定义
  missing_params?: string[]        // 缺失的必填参数
  reply_text: string               // 工具描述
}

interface ParamDefinition {
  label: string
  type: 'text' | 'number' | 'date' | 'select' | 'textarea'
  required: boolean
  placeholder: string
  default_value?: string
  options?: Array<{ value: string; label: string }>
}
```

### 2.2 `disambiguation_required` 事件

```typescript
interface DisambiguationRequiredEvent {
  event: 'disambiguation_required'
  round: number                    // 当前轮数
  tool: string                     // 待执行工具
  params: Record<string, unknown>  // 工具参数（部分）
  entity_type: 'opportunity' | 'contact' | 'contract'  // 实体类型
  candidates: EntityCandidate[]    // 候选列表
  message: string                  // 提示信息
  previous_results?: ExecutedResult[]  // 前几轮执行结果
}

interface EntityCandidate {
  id: number                       // 实体 ID
  name: string                     // 实体名称
  display_info: string             // 展示信息（如金额）
}
```

### 2.3 `awaiting_confirmation` 事件

```typescript
interface AwaitingConfirmationEvent {
  event: 'awaiting_confirmation'
  round: number                    // 当前轮数
  tool_calls: ToolCall[]           // 待确认工具列表
  message: string                  // 提示信息
}
```

### 2.4 `round_completed` 事件

```typescript
interface RoundCompletedEvent {
  event: 'round_completed'
  round: number                    // 完成的轮数
  results: ExecutedResult[]        // 执行结果列表
}

interface ExecutedResult {
  tool: string                     // 工具名
  success: boolean                 // 是否成功
  message: string                  // 结果信息
  data?: unknown                   // 返回数据
}
```

---

## 三、MagicWandDialog.vue 改造方案

### 3.1 新增 Stage 类型

```typescript
// 原有
type Stage = 'input' | 'clarify' | 'preview' | 'preview-form' | 'preview-followup' | 'result'

// 新增
type Stage = 
  | 'input' 
  | 'clarify' 
  | 'preview' 
  | 'preview-form' 
  | 'preview-followup' 
  | 'preview-multi'         // 多工具依次确认
  | 'preview-multi-form'    // 多工具表单填充
  | 'disambiguation'        // 实体歧义选择
  | 'react-progress'        // ReAct 多轮进度展示
  | 'result'
```

### 3.2 新增状态变量

```typescript
// ReAct 相关状态
const reactRound = ref(1)                    // 当前轮数
const maxRounds = ref(5)                     // 最大轮数
const toolCallQueue = ref<ToolCall[]>([])   // 待确认工具队列
const currentToolIndex = ref(0)              // 当前处理工具索引
const executedResults = ref<ExecutedResult[]>([])  // 已执行结果
const previousResults = ref<ExecutedResult[]>([])  // 前几轮结果
const reactMode = ref(false)                 // 是否 ReAct 模式

// 实体歧义状态
const disambiguationCandidates = ref<EntityCandidate[]>([])
const disambiguationEntityType = ref('')
const disambiguationMessage = ref('')
const pendingToolCall = ref<ToolCall | null>(null)  // 待选择后执行的工具
```

### 3.3 SSE 事件处理重构

```typescript
function handleSSEEvent(event: AIAssistantSSEEvent) {
  switch (event.event) {
    case 'status':
      replyText.value = event.message || ''
      break

    case 'content':
      replyText.value += event.content || ''
      break

    case 'parsed':
      // 原有单工具逻辑保持不变
      handleParsedSingle(event)
      break

    case 'parsed_multi':
      // 新增：多工具依次确认
      handleParsedMulti(event)
      break

    case 'disambiguation_required':
      // 新增：实体歧义选择
      handleDisambiguation(event)
      break

    case 'awaiting_confirmation':
      // ReAct 等待确认，前端需要处理用户操作
      handleAwaitingConfirmation(event)
      break

    case 'round_completed':
      // 单轮执行完成，准备进入下一轮
      handleRoundCompleted(event)
      break

    case 'max_rounds_reached':
      // 达到最大轮数
      handleMaxRoundsReached(event)
      break

    case 'result':
      handleResult(event)
      break

    case 'error':
      handleError(event)
      break
  }
}
```

### 3.4 多工具处理流程

```typescript
function handleParsedMulti(event: ParsedMultiEvent) {
  // 设置 ReAct 模式
  reactMode.value = true
  reactRound.value = event.round || 1
  previousResults.value = event.previous_results || []

  // 初始化工具队列
  toolCallQueue.value = event.tool_calls
  currentToolIndex.value = 0

  replyText.value = event.reply_text

  // 判断是否需要表单填充
  const firstCall = event.tool_calls[0]
  if (firstCall?.param_definitions && Object.keys(firstCall.param_definitions).length > 0) {
    // 有参数定义，进入表单填充阶段
    stage.value = 'preview-multi-form'
  } else {
    // 无参数定义，直接预览确认
    stage.value = 'preview-multi'
  }
}
```

### 3.5 依次确认逻辑

```typescript
// 当前工具
const currentToolCall = computed(() => {
  if (toolCallQueue.value.length === 0) return null
  return toolCallQueue.value[currentToolIndex.value]
})

// 是否还有后续工具
const hasMoreTools = computed(() => {
  return currentToolIndex.value < toolCallQueue.value.length - 1
})

// 确认当前工具
async function handleConfirmCurrentTool() {
  if (!currentToolCall.value) return

  isExecuting.value = true

  try {
    // 执行单个工具
    const result = await executeSingleTool(
      currentToolCall.value.tool,
      currentToolCall.value.params
    )

    // 记录执行结果
    executedResults.value.push({
      tool: currentToolCall.value.tool,
      success: result.success,
      message: result.message,
      data: result.data
    })

    // 显示单个工具结果（短暂提示）
    if (result.success) {
      ElMessage.success(`${getToolDisplayName(currentToolCall.value.tool)} 执行成功`)
    } else {
      ElMessage.error(`${getToolDisplayName(currentToolCall.value.tool)} 执行失败：${result.message}`)
    }

    // 判断是否有下一个工具
    if (hasMoreTools.value) {
      // 进入下一个工具
      currentToolIndex.value++
      
      // 判断下一个工具是否需要表单
      const nextCall = toolCallQueue.value[currentToolIndex.value]
      if (nextCall?.param_definitions && Object.keys(nextCall.param_definitions).length > 0) {
        stage.value = 'preview-multi-form'
      } else {
        stage.value = 'preview-multi'
      }
    } else {
      // 本轮所有工具完成，准备进入下一轮（ReAct 模式）
      if (reactMode.value) {
        stage.value = 'react-progress'
        // 调用 continue_react 进入下一轮
        await continueReactRound()
      } else {
        // 非 ReAct 模式，显示最终结果
        showFinalResult()
      }
    }
  } catch (error) {
    // 执行失败，记录并继续处理下一个工具（不中断）
    executedResults.value.push({
      tool: currentToolCall.value.tool,
      success: false,
      message: error.message
    })

    if (hasMoreTools.value) {
      currentToolIndex.value++
      // 继续下一个工具...
    } else {
      showFinalResult()
    }
  } finally {
    isExecuting.value = false
  }
}

// 跳过当前工具
function handleSkipCurrentTool() {
  executedResults.value.push({
    tool: currentToolCall.value.tool,
    success: false,
    message: '用户跳过'
  })

  if (hasMoreTools.value) {
    currentToolIndex.value++
    // 更新 stage...
  } else {
    showFinalResult()
  }
}

// 取消后续所有工具
function handleCancelAllTools() {
  stage.value = 'result'
  success.value = executedResults.value.some(r => r.success)
  
  const successCount = executedResults.value.filter(r => r.success).length
  const skipCount = executedResults.value.filter(r => !r.success).length
  
  resultMessage.value = `已完成 ${successCount} 个操作，跳过 ${skipCount} 个操作`
}
```

### 3.6 ReAct 继续下一轮

```typescript
async function continueReactRound() {
  if (reactRound.value >= maxRounds.value) {
    // 达到最大轮数，显示完成
    stage.value = 'result'
    success.value = true
    resultMessage.value = '多轮处理已完成（达到最大轮数限制）'
    return
  }

  isLoading.value = true
  replyText.value = 'AI 继续分析...'

  try {
    await aiAssistantApi.continueReactSSE(
      {
        round: reactRound.value,
        original_content: userInput.value,
        executed_results: executedResults.value
      },
      (event: AIAssistantSSEEvent) => {
        handleSSEEvent(event)
      },
      token
    )
  } catch (error) {
    ElMessage.error('继续处理失败')
    stage.value = 'result'
    success.value = false
    resultMessage.value = '处理中断'
  } finally {
    isLoading.value = false
  }
}
```

---

## 四、新增组件详解

### 4.1 ReactProgress.vue

**用途**：展示 ReAct 多轮进度，显示每轮执行的工具和结果。

**Props**：
```typescript
interface ReactProgressProps {
  currentRound: number            // 当前轮数
  maxRounds: number               // 最大轮数
  previousResults: ExecutedResult[]  // 前几轮结果
  currentRoundResults?: ExecutedResult[]  // 当前轮结果
  isLoading?: boolean             // 是否加载中
}
```

**模板结构**：
```vue
<template>
  <div class="react-progress">
    <!-- 轮数进度条 -->
    <div class="round-indicator">
      <span class="round-label">Round {{ currentRound }}/{{ maxRounds }}</span>
      <el-progress 
        :percentage="(currentRound / maxRounds) * 100" 
        :show-text="false"
      />
    </div>

    <!-- 已完成轮数展示 -->
    <div v-if="previousResults.length > 0" class="previous-rounds">
      <div class="round-header">
        <el-icon><Check /></el-icon>
        <span>已完成 Round {{ currentRound - 1 }}</span>
      </div>
      <div class="round-tools">
        <div 
          v-for="result in previousResults" 
          :key="result.tool"
          class="tool-result"
        >
          <span class="tool-name">{{ getToolDisplayName(result.tool) }}</span>
          <el-tag :type="result.success ? 'success' : 'danger'" size="small">
            {{ result.success ? '成功' : '失败' }}
          </el-tag>
        </div>
      </div>
    </div>

    <!-- 当前轮加载状态 -->
    <div v-if="isLoading" class="current-loading">
      <el-icon class="is-loading"><Loading /></el-icon>
      <span>AI 正在分析下一步操作...</span>
    </div>
  </div>
</template>
```

### 4.2 EntitySelectDialog.vue

**用途**：实体歧义时，展示候选列表让用户选择。

**Props**：
```typescript
interface EntitySelectProps {
  visible: boolean
  entityType: 'opportunity' | 'contact' | 'contract'
  candidates: EntityCandidate[]
  message: string
}
```

**Emits**：
```typescript
interface EntitySelectEmits {
  (e: 'update:visible', value: boolean): void
  (e: 'select', candidate: EntityCandidate): void  // 用户选择
  (e: 'cancel'): void  // 用户取消
}
```

**模板结构**：
```vue
<template>
  <el-dialog
    v-model="visible"
    title="请选择实体"
    width="500px"
    :close-on-click-modal="false"
  >
    <div class="entity-select">
      <!-- 提示信息 -->
      <div class="select-message">
        <el-icon><WarningFilled /></el-icon>
        <span>{{ message }}</span>
      </div>

      <!-- 候选列表 -->
      <div class="candidate-list">
        <div 
          v-for="candidate in candidates" 
          :key="candidate.id"
          class="candidate-item"
          :class="{ 'selected': selectedId === candidate.id }"
          @click="selectedId = candidate.id"
        >
          <el-radio :value="candidate.id" :label="candidate.id">
            <div class="candidate-content">
              <span class="candidate-name">{{ candidate.name }}</span>
              <span class="candidate-info">{{ candidate.display_info }}</span>
            </div>
          </el-radio>
        </div>
      </div>
    </div>

    <template #footer>
      <el-button @click="handleCancel">取消</el-button>
      <el-button 
        type="primary" 
        :disabled="!selectedId"
        @click="handleConfirm"
      >
        确认选择
      </el-button>
    </template>
  </el-dialog>
</template>
```

---

## 五、API 扩展

### 5.1 新增 continue_react 接口

```typescript
// api/aiAssistant.ts 扩展

export interface ContinueReactRequest {
  round: number
  original_content: string
  executed_results: ExecutedResult[]
}

export interface AIAssistantSSEEvent {
  event: 'status' | 'content' | 'parsed' | 'parsed_multi' | 
         'disambiguation_required' | 'awaiting_confirmation' | 
         'round_completed' | 'max_rounds_reached' | 'result' | 'error'
  // ... 其他字段同上
  round?: number
  tool_calls?: ToolCall[]
  entity_type?: string
  candidates?: EntityCandidate[]
  previous_results?: ExecutedResult[]
}

export const aiAssistantApi = {
  // 原有 chatSSE...

  /**
   * 继续 ReAct 循环（SSE 流式响应）
   */
  continueReactSSE: async (
    data: ContinueReactRequest,
    onEvent: (event: AIAssistantSSEEvent) => void,
    token: string
  ): Promise<void> => {
    const url = '/api/v1/assistant/continue-react'
    
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify(data)
    })

    if (!response.ok) {
      const errorText = await response.text()
      throw new Error(`HTTP error: ${response.status} - ${errorText}`)
    }

    const reader = response.body?.getReader()
    if (!reader) {
      throw new Error('No response body')
    }

    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const eventData = JSON.parse(line.slice(6)) as AIAssistantSSEEvent
            onEvent(eventData)

            if (eventData.event === 'result' || eventData.event === 'error') {
              return
            }
          } catch {
            // 忽略解析错误
          }
        }
      }
    }
  }
}
```

---

## 六、交互流程图

### 6.1 单工具流程（原有）

```
用户输入 → parsed → preview-form → 用户填充 → execute → result
```

### 6.2 多工具依次确认流程

```
用户输入 → parsed_multi → preview-multi → 
  工具1确认 → 执行 → 
  工具2确认 → 执行 → 
  ... → 
  全部完成 → result
```

### 6.3 ReAct 多轮流程

```
用户输入 → parsed_multi (Round 1) → 
  工具1确认 → 执行 → 
  工具2确认 → 执行 → 
  Round 1 完成 → react-progress → 
  continue_react → 
  parsed_multi (Round 2) → 
  工具3确认 → 执行 → 
  ... → 
  AI 判断完成 → result
```

### 6.4 实体歧义流程

```
用户输入 → parsed_multi → 
  检测到歧义 → disambiguation_required → 
  EntitySelectDialog → 用户选择 → 
  继续执行工具 → ...
```

---

## 七、任务清单

### 7.1 组件开发

| 任务 | 文件 | 预估工时 | 优先级 |
|------|------|----------|--------|
| 扩展 SSE 事件类型定义 | `api/aiAssistant.ts` | 0.5h | P0 |
| 新增 continue_react 接口 | `api/aiAssistant.ts` | 1h | P0 |
| 新增 Stage 类型 + 状态变量 | `MagicWandDialog.vue` | 1h | P0 |
| 实现 parsed_multi 处理逻辑 | `MagicWandDialog.vue` | 2h | P0 |
| 实现依次确认 UI（preview-multi stage） | `MagicWandDialog.vue` | 2h | P0 |
| 实现依次确认表单（preview-multi-form stage） | `MagicWandDialog.vue` | 2h | P1 |
| 实现 disambiguation_required 处理 | `MagicWandDialog.vue` | 1h | P1 |
| 实现 continueReactRound 逻辑 | `MagicWandDialog.vue` | 1h | P1 |
| 实现 ReactProgress 组件 | `ReactProgress.vue` | 1h | P1 |
| 实现 EntitySelectDialog 组件 | `EntitySelectDialog.vue` | 1h | P2 |
| 优化样式 + 交互细节 | 全部组件 | 1h | P2 |
| 单元测试 | `tests/unit/` | 2h | P3 |
| E2E 测试 | `tests/e2e/` | 2h | P3 |

**总计**：约 14.5h（约 2 工作日）

### 7.2 开发顺序建议

**Day 1**：
1. 扩展 API 类型 + continue_react 接口
2. 新增 Stage + 状态变量
3. 实现 parsed_multi 处理
4. 实现依次确认 UI（preview-multi）

**Day 2**：
5. 实现依次确认表单（preview-multi-form）
6. 实现 disambiguation 处理
7. 实现 continueReactRound
8. 实现 ReactProgress + EntitySelectDialog
9. 优化样式 + 测试

### 7.3 测试文件

| 测试文件 | 路径 | 说明 |
|----------|------|------|
| 集成测试 | `CRM-Server/tests/unit/test_phase6_frontend.py` | 类型结构验证 + 流程逻辑测试 |

---

## 八、验收标准

### 8.1 功能验收

| 验收项 | 标准 |
|--------|------|
| parsed_multi 处理 | 收到多工具事件后，依次展示确认弹窗 |
| 依次确认 | 用户可"确认"、"跳过"、"取消后续" |
| 表单填充 | 有参数定义时，展示表单让用户确认/修改 |
| ReAct 多轮 | 多轮时显示进度（Round 1/5），完成后自动进入下一轮 |
| 实体歧义 | 收到 disambiguation_required 后展示选择界面 |
| 选择后继续 | 用户选择实体后，继续执行工具 |
| 向后兼容 | 单工具模式下行为不变 |

### 8.2 UI 验收

| 验收项 | 标准 |
|--------|------|
| 轮数进度 | 清晰显示当前轮数和最大轮数 |
| 工具进度 | 清晰显示当前工具是第几个 |
| 执行结果 | 每个工具执行后显示成功/失败提示 |
| 歧义选择 | 候选列表清晰，包含名称和关键信息 |
| 操作按钮 | "确认"、"跳过"、"取消"按钮清晰可见 |

---

## 九、风险与应对

| 风险 | 影响 | 应对措施 |
|------|------|----------|
| SSE 事件类型扩展导致原有逻辑失效 | 单工具模式失效 | 保持 `parsed` 事件原有逻辑不变 |
| ReAct 多轮状态管理复杂 | 状态混乱 | 清晰划分 ReAct 状态和非 ReAct 状态 |
| 依次确认交互复杂 | 用户体验差 | 提供快捷操作（全部确认、全部跳过） |
| 实体歧义频繁触发 | 用户疲劳 | 后端已限制候选数量，前端展示优化 |

---

## 十、参考文档

- [AI-TOOL-ENHANCEMENT-PLAN.md](./AI-TOOL-ENHANCEMENT-PLAN.md) - 整体实施计划
- [AI-TOOL-ENHANCEMENT-REQUIREMENTS.md](../requirements/AI-TOOL-ENHANCEMENT-REQUIREMENTS.md) - 需求文档
- [COMPONENTS.md](../../CRM-Client/docs/COMPONENTS.md) - 组件开发规范

---

> **文档版本**：1.0
> **最后更新**：2026-06-09
> **维护团队**：CRMWolf 开发团队