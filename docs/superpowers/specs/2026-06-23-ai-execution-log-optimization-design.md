# AI 执行日志优化设计文档

**创建时间**: 2026-06-23
**设计方法**: superpowers brainstorming skill + 系统开发规范
**实施范围**: Phase 1-3 全面修复实施

---

## 📋 设计概览

### 核心目标

解决 AI 执行日志展示的三大痛点：
1. **占用空间大** → 紧凑轨迹设计（收起状态仅 44px）
2. **不符合设计系统 token** → 使用 `$wolf-*` Sass 变量 + Signature 元素
3. **刷新丢失** → 持久化存储到对话历史

### 实施范围

| Phase | 内容 | 设计文档标注 | 实际排查状态 |
|-------|------|--------------|--------------|
| **Phase 1** | UI 优化（前端） | ✅ 已完成 | ❌ 存在 7 个关键缺陷 |
| **Phase 2** | 持久化改造（前后端） | ⏳ 待实施 | ⏳ 待实施 |
| **Phase 3** | 用户体验优化 | ⏳ 待实施 | ⏳ 待实施 |

### Phase 1 缺陷清单

| # | 缺陷项 | 设计要求 | 实际状态 |
|---|--------|----------|----------|
| 1 | **CompactExecutionLog.vue 缺失** | 创建新的紧凑轨迹组件 | ❌ 不存在 |
| 2 | **状态颜色区分不完整** | 思考中 `$wolf-primary`、成功 `$wolf-success-text`、失败 `$wolf-danger-text` | ⚠️ 仅图标区分，无颜色 |
| 3 | **空状态设计不符规范** | "AI 准备就绪，等待你的指令" + 温暖提示 | ❌ 显示冷冰冰的 "暂无执行记录" |
| 4 | **进度计数缺失** | "Round 2/5 · 正在查询客户信息" | ❌ 未实现 |
| 5 | **键盘导航缺失** | Tab/Enter/Escape + ARIA 属性 | ❌ 未实现 |
| 6 | **focus 状态样式缺失** | `focus-visible` outline 反馈 | ❌ 未实现 |
| 7 | **智能边界线缺失** | Signature 元素：流动感渐变线条 | ❌ 未实现 |

---

## 🎨 Phase 1: UI 优化修复设计

### 整体架构设计

**组件结构**：

```
AgentExecutionLog.vue (现有组件)
├── CompactExecutionLog.vue (新增组件 - 紧凑轨迹核心)
│   ├── CollapsedView.vue (子组件 - 收起状态)
│   ├── ExpandedView.vue (子组件 - 展开状态)
│   ├── EmptyState.vue (子组件 - 空状态)
│   └── SmartBoundaryLine.vue (子组件 - Signature 智能边界线)
├── ThinkingBubble.vue (现有组件)
└── StatusCard.vue (现有组件)
```

**设计原则**：
- **单一职责**：每个子组件只负责一个视觉状态（收起/展开/空状态）
- **状态驱动**：通过 props 控制状态切换，避免内部状态管理
- **可测试性**：每个子组件独立测试，便于验证

**数据流**：

```
AIAssistant.vue (父页面)
  └─> AgentExecutionLog.vue (容器组件)
       ├─> props: steps, expanded
       ├─> emit: toggle-expand
       └─> CompactExecutionLog.vue (核心渲染)
            ├─> CollapsedView.vue (steps.length > 0 && !expanded)
            ├─> ExpandedView.vue (steps.length > 0 && expanded)
            └─> EmptyState.vue (steps.length === 0)
```

---

### 状态颜色设计（修复缺陷 #2）

**状态颜色映射表**：

| 状态 | 文字颜色 | 图标颜色 | 背景色 | Sass 变量引用 |
|------|----------|----------|--------|---------------|
| **思考中** | `$wolf-text-primary` | `$wolf-primary` | `$wolf-bg-ai-message` | `#1C1C1C` / `#4A6FA5` / `#F0F4F8` |
| **执行中** | `$wolf-text-primary` | `$wolf-primary` + rotate | `$wolf-bg-card` | `#1C1C1C` / `#4A6FA5` / `#FFFFFF` |
| **成功** | `$wolf-success-text` | `$wolf-success-text` | `$wolf-success-bg` | `#2B633C` / `#2B633C` / 浅绿背景 |
| **失败** | `$wolf-danger-text` | `$wolf-danger-text` | `$wolf-danger-bg` | `#7A2828` / `#7A2828` / 浅红背景 |

**实现方式**：

```scss
// CollapsedView.vue 状态颜色样式
.status-icon {
  &.is-thinking { color: $wolf-primary; }
  &.is-running { 
    color: $wolf-primary;
    animation: rotate 1s linear infinite;
  }
  &.is-success { color: $wolf-success-text; }
  &.is-error { color: $wolf-danger-text; }
}
```

---

### 空状态设计（修复缺陷 #3）

**设计目标**：温暖提示 + 首次用户引导，消除"无数据"冷感。

**空状态布局**：

```
┌─────────────────────────────────────────────────┐
│                                                 │
│        [Cpu 图标 24px $wolf-primary]            │
│                                                 │
│     "AI 准备就绪，等待你的指令"                  │
│     $wolf-text-secondary 14px                  │
│                                                 │
│  ┌───────────────────────────────────────┐     │
│  │ 💡 输入指令后，AI 的执行过程会在这里    │     │ ← 首次提示（可关闭）
│  │    实时展示                            │     │
│  │                       [知道了 按钮]     │     │
│  └───────────────────────────────────────┘     │
│                                                 │
└─────────────────────────────────────────────────┘
```

**实现方式**：
- 使用 `<Cpu />` SVG 图标（替代现有的 `<Document />`）
- 文案改为"AI 准备就绪，等待你的指令"
- 添加首次提示气泡（`$wolf-bg-ai-message` 背景），3秒自动消失或用户点击"知道了"关闭
- 使用 localStorage 存储 `hasSeenExecutionLogTip` 标记，避免重复显示

---

### 进度计数设计（修复缺陷 #4）

**设计目标**：收起状态显示"Round N/M · 当前步骤"，增强进度可见性。

**布局结构**：

```
┌─────────────────────────────────────────────────┐
│ [状态图标] Round 2/5 · 正在查询客户信息  [展开 →] │
└─────────────────────────────────────────────────┘
```

**实现逻辑**：

```typescript
// 计算总轮次数
const totalRounds = computed(() => {
  const rounds = props.steps.map(s => s.round).filter(Boolean)
  return Math.max(...rounds) || 0
})

// 计算当前轮次
const currentRound = computed(() => {
  const runningStep = props.steps.find(s => s.type === ExecutionStepType.TOOL_CALL)
  return runningStep?.round || totalRounds.value
})

// 格式化进度文本
const progressText = computed(() => {
  if (totalRounds.value === 0) return ''
  return `Round ${currentRound.value}/${totalRounds.value} · `
})
```

---

### 无障碍设计（修复缺陷 #5、#6）

**键盘导航流程**：

```
用户 Tab 进入容器
  → Enter/Space 展开
    → Tab 在步骤卡片间移动
      → Escape 收起
        → Tab 继续到下一个元素
```

**键盘事件处理**：

```typescript
const handleKeydown = (event: KeyboardEvent) => {
  switch (event.key) {
    case 'Enter':
    case 'Space':
      if (!props.expanded) {
        emit('toggle-expand')
        event.preventDefault()
      }
      break
    case 'Escape':
      if (props.expanded) {
        emit('toggle-expand')
        event.preventDefault()
      }
      break
  }
}
```

**Focus 样式规范**：

```scss
.collapsed-view {
  cursor: pointer;
  
  &:focus-visible {
    outline: 2px solid $wolf-primary;
    outline-offset: 2px;
    box-shadow: 0 0 0 4px rgba($wolf-primary, 0.15);
  }
}

.step-item:focus-visible {
  outline: 2px solid $wolf-primary;
  outline-offset: 1px;
}
```

**ARIA 属性完整规范**：

```html
<div 
  role="log" 
  aria-label="AI 执行进度"
  class="agent-execution-log"
>
  <!-- 空状态 -->
  <div 
    v-if="steps.length === 0"
    role="status" 
    aria-live="polite"
    aria-label="AI 就绪状态"
  >
    <el-icon><Cpu /></el-icon>
    <span>AI 准备就绪，等待你的指令</span>
  </div>
  
  <!-- 收起状态（可交互） -->
  <div 
    v-else-if="!expanded"
    role="button"
    aria-expanded="false"
    aria-controls="expanded-view"
    tabindex="0"
    class="collapsed-view"
  >
    ...
  </div>
  
  <!-- 展开状态 -->
  <div 
    v-else
    id="expanded-view"
    aria-live="polite"
    class="expanded-view"
  >
    <div 
      v-for="step in steps"
      role="listitem" 
      aria-label="Round {{ step.round }} - {{ step.title }}"
      tabindex="0"
      class="step-item"
    >
      ...
    </div>
  </div>
</div>
```

**Reduced Motion 支持**：

```scss
@media (prefers-reduced-motion: reduce) {
  .collapsed-view .status-icon.is-running {
    animation: none;
  }
  
  .agent-execution-log * {
    transition: none !important;
    animation: none !important;
  }
}
```

---

### Signature 智能边界线设计（修复缺陷 #7）

**Signature 元素定义**（DESIGN-PRINCIPLES.md 1.0）：

| Signature | 实现 | 位置 |
|-----------|------|------|
| **智能边界线** | 流动感渐变线条 | `AgentExecutionLog.vue` 容器顶部 |

**视觉效果**：

```
┌─────────────────────────────────────────────────┐
│ ══════════════ 智能边界线 ════════════════     │ ← 流动感渐变线条
│                                                 │
│ [状态图标] Round 2/5 · 正在查询客户信息  [展开 →] │
└─────────────────────────────────────────────────┘
```

**实现方式**：

```scss
.smart-boundary-line {
  height: 2px;
  background: linear-gradient(
    90deg,
    transparent 0%,
    $wolf-primary 20%,
    $wolf-primary 80%,
    transparent 100%
  );
  
  &.is-active {
    animation: flow 2s ease-in-out infinite;
  }
}

@keyframes flow {
  0%, 100% {
    transform: scaleX(0.8);
    opacity: 0.6;
  }
  50% {
    transform: scaleX(1);
    opacity: 1;
  }
}

@media (prefers-reduced-motion: reduce) {
  .smart-boundary-line.is-active {
    animation: none;
    opacity: 0.8;
  }
}
```

---

## 🔄 Phase 2: 持久化改造设计

### 数据结构调整

**扩展对话消息类型**：

```typescript
interface ConversationMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  executionSteps?: ExecutionStep[]
}
```

**后端数据模型调整**：

```python
class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"))
    role = Column(String(20))
    content = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)
    execution_steps = Column(JSON, nullable=True)
```

---

### API 适配

**Pydantic Schema 扩展**：

```python
class ExecutionStepSchema(BaseModel):
    id: str
    type: str
    title: str
    description: Optional[str] = None
    timestamp: datetime
    round: Optional[int] = None
    tool: Optional[str] = None
    params: Optional[dict] = None
    result: Optional[dict] = None
    success: Optional[bool] = None
    error: Optional[str] = None

class ConversationMessageSchema(BaseModel):
    id: int
    role: str
    content: str
    timestamp: datetime
    execution_steps: Optional[List[ExecutionStepSchema]] = None
```

**Zod Schema 扩展**：

```typescript
const ExecutionStepSchema = z.object({
  id: z.string(),
  type: z.enum(['ROUND_START', 'TOOL_CALL', 'TOOL_RESULT', 'ROUND_COMPLETED', 'REACT_COMPLETE', 'ERROR']),
  title: z.string(),
  description: z.string().optional(),
  timestamp: z.coerce.date(),
  round: z.number().optional(),
  tool: z.string().optional(),
  params: z.record(z.any()).optional(),
  result: z.record(z.any()).optional(),
  success: z.boolean().optional(),
  error: z.string().optional()
})

const ConversationMessageSchema = z.object({
  id: z.number(),
  role: z.enum(['user', 'assistant']),
  content: z.string(),
  timestamp: z.coerce.date(),
  execution_steps: z.array(ExecutionStepSchema).optional()
})
```

**数据库迁移脚本**：

```python
def upgrade():
    op.add_column(
        'conversation_messages',
        sa.Column('execution_steps', sa.JSON, nullable=True)
    )

def downgrade():
    op.drop_column('conversation_messages', 'execution_steps')
```

---

### 前后端存储逻辑

**SSE 流结束存储逻辑**：

```typescript
const handleSSEEvent = (event: SSEEvent) => {
  const step = mapSSEEventToStep(event)
  executionSteps.value.push(step)
  
  if (event.type === 'REACT_COMPLETE' || event.type === 'ERROR') {
    saveExecutionStepsToCurrentMessage()
  }
}

const saveExecutionStepsToCurrentMessage = () => {
  const currentAIMessage = currentConversationStore.currentAIMessage
  if (currentAIMessage) {
    currentAIMessage.executionSteps = executionSteps.value
    currentConversationStore.updateMessage(currentAIMessage.id, {
      execution_steps: executionSteps.value
    })
  }
}
```

**保存对话同步逻辑**：

```typescript
const saveConversation = async (conversationId: number) => {
  const messages = conversationMessages.value.map(msg => ({
    id: msg.id,
    role: msg.role,
    content: msg.content,
    timestamp: msg.timestamp,
    execution_steps: msg.executionSteps || undefined
  }))
  
  await api.saveConversation(conversationId, { messages })
}
```

**加载历史对话恢复逻辑**：

```typescript
const loadConversation = async (conversationId: number) => {
  const response = await api.getConversation(conversationId)
  
  conversationMessages.value = response.messages.map(msg => ({
    ...msg,
    executionSteps: msg.execution_steps || []
  }))
  
  const lastAIMessage = conversationMessages.value
    .filter(msg => msg.role === 'assistant')
    .pop()
  
  if (lastAIMessage?.executionSteps) {
    const agentExecutionLog = useAgentExecutionLog()
    agentExecutionLog.executionSteps.value = lastAIMessage.executionSteps
  }
}
```

---

### 刷新恢复机制

**页面初始化恢复逻辑**：

```typescript
onMounted(async () => {
  const conversationId = getCurrentConversationId()
  
  if (conversationId) {
    await conversation.loadConversation(conversationId)
    
    const lastAIMessage = conversation.messages.value
      .filter(msg => msg.role === 'assistant')
      .pop()
    
    if (lastAIMessage?.executionSteps) {
      agentExecutionLog.executionSteps.value = lastAIMessage.executionSteps
      console.log('[Refresh Recovery] Restored execution steps:', {
        count: lastAIMessage.executionSteps.length
      })
    }
  }
})
```

**localStorage 临时缓存（可选）**：

```typescript
watch(executionSteps, (newSteps) => {
  if (newSteps.length > 0) {
    localStorage.setItem(
      `execution_steps_${getCurrentConversationId()}`,
      JSON.stringify(newSteps)
    )
  }
}, { deep: true })

const restoreFromLocalStorage = () => {
  const cachedSteps = localStorage.getItem(
    `execution_steps_${getCurrentConversationId()}`
  )
  
  if (cachedSteps) {
    executionSteps.value = JSON.parse(cachedSteps)
  }
}
```

---

## 🎭 Phase 3: 用户体验优化设计

### 自动收起逻辑

**设计目标**：执行完成后 3 秒自动收起，UI 清洁 + 用户注意力转向结果。

**实现方式**：

```typescript
const isExecutionComplete = computed(() => {
  const lastStep = executionSteps.value[executionSteps.value.length - 1]
  return lastStep?.type === 'REACT_COMPLETE' || lastStep?.type === 'ERROR'
})

let autoCollapseTimer: number | null = null

watch(isExecutionComplete, (isComplete) => {
  if (isComplete && expanded.value) {
    autoCollapseTimer = setTimeout(() => {
      expanded.value = false
    }, 3000)
  }
})

const handleToggleExpand = () => {
  expanded.value = !expanded.value
  if (expanded.value) {
    clearTimeout(autoCollapseTimer)
  }
}
```

**自动收起视觉反馈**：

```vue
<div 
  v-if="isExecutionComplete && expanded && autoCollapseCountdown > 0"
  class="auto-collapse-hint"
>
  <span>执行完成，{{ autoCollapseCountdown }}秒后自动收起</span>
  <button @click="cancelAutoCollapse">保持展开</button>
</div>
```

---

### 悬停预览功能

**设计目标**：收起状态下，鼠标悬停显示简要信息，快速了解执行进度。

**Tooltip 内容**：

```typescript
const hoverPreviewContent = computed(() => {
  const totalRounds = Math.max(...props.steps.map(s => s.round || 0))
  const currentRound = props.steps.find(s => s.type === 'TOOL_CALL')?.round || totalRounds
  
  return {
    progress: `Round ${currentRound}/${totalRounds}`,
    currentStep: currentStep.value?.title || '正在处理...',
    status: isRunning.value ? '执行中' : isSuccess.value ? '已完成' : '失败',
    timeElapsed: calculateElapsedTime(props.steps)
  }
})
```

**Tooltip UI 设计**：

```vue
<div v-if="hoverPreviewVisible" class="hover-preview-tooltip">
  <div class="tooltip-header">
    <span class="progress-label">{{ hoverPreviewContent.progress }}</span>
    <span class="status-label">{{ hoverPreviewContent.status }}</span>
  </div>
  <div class="tooltip-body">
    <p class="current-step">{{ hoverPreviewContent.currentStep }}</p>
    <p class="time-elapsed">执行时长: {{ hoverPreviewContent.timeElapsed }}</p>
  </div>
  <div class="tooltip-footer">
    <span class="hint">点击查看完整轨迹</span>
  </div>
</div>
```

---

### 轨迹导航功能

**设计目标**：点击步骤卡片跳转到对应消息，建立"AI行为"与"用户提问"的链接。

**步骤卡片跳转逻辑**：

```typescript
interface Props {
  steps: ExecutionStep[]
  expanded: boolean
  stepToMessageMap?: Record<string, number>
}

const emit = defineEmits<{
  (e: 'toggle-expand'): void
  (e: 'navigate-to-message', messageId: number): void
}>()

const handleStepClick = (step: ExecutionStep) => {
  const messageId = props.stepToMessageMap?.[step.id]
  if (messageId) {
    emit('navigate-to-message', messageId)
  }
}
```

**步骤 ID 与消息 ID 映射**：

```typescript
const stepToMessageMap = computed(() => {
  const map: Record<string, number> = {}
  
  for (const message of messages.value) {
    if (message.role === 'assistant' && message.executionSteps) {
      for (const step of message.executionSteps) {
        map[step.id] = message.id
      }
    }
  }
  
  return map
})
```

**跳转到消息 UI 实现**：

```typescript
const handleNavigateToMessage = (messageId: number) => {
  const messageElement = document.getElementById(`message-${messageId}`)
  
  if (messageElement) {
    messageElement.scrollIntoView({
      behavior: 'smooth',
      block: 'center'
    })
    
    messageElement.classList.add('highlighted')
    setTimeout(() => {
      messageElement.classList.remove('highlighted')
    }, 2000)
  }
}
```

---

## 📋 实施清单（更新）

### Phase 1: UI 优化修复（前端）

1. ✅ 创建 CompactExecutionLog.vue 组件架构设计
2. ⏳ 创建 CollapsedView.vue 子组件（收起状态）
3. ⏳ 创建 ExpandedView.vue 子组件（展开状态）
4. ⏳ 创建 EmptyState.vue 子组件（空状态）
5. ⏳ 创建 SmartBoundaryLine.vue 子组件（Signature 元素）
6. ⏳ 实现状态颜色区分（4 种状态）
7. ⏳ 实现进度计数显示（Round N/M）
8. ⏳ 实现键盘导航 + ARIA 属性
9. ⏳ 实现 focus 状态样式
10. ⏳ 重构 AgentExecutionLog.vue 为容器组件

### Phase 2: 持久化改造（前后端）

1. ⏳ 扩展 ConversationMessage 类型（前端）
2. ⏳ 新增 execution_steps 字段（后端数据模型）
3. ⏳ 编写数据库迁移脚本（Alembic）
4. ⏳ 扩展 Pydantic/Zod Schema（前后端）
5. ⏳ 实现 SSE 流结束存储逻辑（前端）
6. ⏳ 实现保存对话同步逻辑（前端）
7. ⏳ 实现后端存储逻辑（后端 CRUD）
8. ⏳ 实现加载历史对话恢复逻辑（前端）
9. ⏳ 实现刷新恢复机制（前端）
10. ⏳ 实现 localStorage 临时缓存（可选）

### Phase 3: 用户体验优化（前端）

1. ⏳ 实现自动收起逻辑（3 秒倒计时）
2. ⏳ 实现自动收起视觉反馈（提示气泡）
3. ⏳ 实现用户取消自动收起功能
4. ⏳ 实现悬停预览 Tooltip（进度摘要）
5. ⏳ 实现轨迹导航功能（步骤 → 消息跳转）
6. ⏳ 实现步骤 ID 与消息 ID 映射
7. ⏳ 实现消息高亮样式（跳转后高亮 2 秒）

---

## 🎯 设计目标验证（更新）

| 用户痛点 | 解决方案 | 验证方式 |
|----------|----------|----------|
| 占用空间大 | 收起状态仅 1 行（44px） | 视觉检查 |
| 不符合设计系统 token | 使用 `$wolf-*` Sass 变量 + Signature 智能边界线 | 视觉检查 |
| 缺少状态颜色区分 | 颜色 + 图标双重区分 + 背景 tone 区分 | 视觉检查 |
| 空状态冷感 | 温暖提示 + 首次用户引导 | 用户测试 |
| 缺少进度可见性 | Round N/M 进度计数 | 功能测试 |
| 无障碍缺失 | 键盘导航 + ARIA 属性 + focus 状态 | WCAG 审计 |
| 刷新丢失 | 持久化存储到对话历史 + localStorage 缓存 | 功能测试 |
| 缺少自动收起 | 3 秒自动收起 + 视觉反馈 | 用户测试 |
| 缺少悬停预览 | Tooltip 显示进度摘要 | 用户测试 |
| 缺少轨迹导航 | 点击步骤跳转到消息 | 功能测试 |

---

## 📝 设计决策记录（更新）

| 决策项 | 选择 | 原因 |
|--------|------|------|
| **组件架构** | ✅ 子组件拆分（CollapsedView/ExpandedView/EmptyState） | 单一职责 + 可测试性 |
| **持久化方案** | ✅ 存储到数据库 + localStorage 缓存 | 解决 "刷新丢失" 痛点 + SSE中断保护 |
| **自动收起逻辑** | ✅ 执行完成后 3 秒自动收起 + 视觉反馈 | UI 清洁 + 用户注意力转向结果 |
| **悬停预览** | ✅ Tooltip 显示进度摘要 + 执行时长 | 快速了解进度，不打断流程 |
| **轨迹导航** | ✅ 点击步骤卡片跳转到对应消息 | 建立 "AI行为" 与 "用户提问" 的链接 |
| **Signature 元素** | ✅ 智能边界线（流动感渐变线条） | DESIGN-PRINCIPLES.md 要求的独特视觉标识 |

---

## 🔗 相关文档

- **原始设计文档**: `CRM-Docs/system/design/AI-THINKING-PROCESS-DESIGN.md`
- **设计原则**: `CRM-Client/docs/DESIGN-PRINCIPLES.md`
- **系统架构**: `CRM-Docs/system/ARCHITECTURE.md`
- **设计 Token**: `CRM-Client/src/styles/variables.scss`
- **组件模板**: `CRM-Client/docs/COMPONENTS.md`
- **TypeScript 规范**: `CRM-Client/docs/TYPESCRIPT.md`

---

**版本**: 1.0 | **创建时间**: 2026-06-23 | **设计方法**: superpowers brainstorming skill