# AgentExecutionLog 诊断计划

## 发现的 Root Causes

### RC-1: 工具名称未业务化

**证据**：
- 前端 ToolTitleMap: `create_follow_up`
- 后端工具名称: `follow_up_customer`
- 用户看到: `follow_up_customer`（技术名称）

**位置**：
- `CRM-Client/src/types/agentExecution.ts:124-147`（ToolTitleMap 缺少 `follow_up_customer`）
- `CRM-Server/app/services/agent/tools.py:180-220`（后端定义 `follow_up_customer`）

---

### RC-2: ThinkingBubble 和业务参数重复

**证据**：
- ThinkingBubble 显示 `step.description`
- business-params 显示 `formatBusinessParams(step.params, step.title)`
- 两者内容相同，导致重复显示

**位置**：
- `CRM-Client/src/components/AgentExecutionLog.vue:44-56`
- `CRM-Client/src/composables/useAgentExecutionLog.ts:156-178`

---

### RC-3: 缺少 AI 思考过程内容

**证据**：
- 需求文档要求 ThinkingBubble 显示"AI 推理过程"
- 当前 `step.description` 存储的是业务化参数（不是思考过程）
- 后端 SSE 事件可能没有发送 AI 思考过程内容

**位置**：
- `CRM-Server/app/services/agent/sse_streamer.py:71-79`
- `CRM-Client/src/composables/useAgentExecutionLog.ts:156-178`

---

### RC-4: AI 回复文本重复

**证据**：
- 用户看到："已为光大证券股份有限公司创建跟进记录..." 出现两次
- 可能是 SSE 事件 `result` 和 `complete` 都发送了相同内容

**位置**：
- `CRM-Server/app/services/agent/sse_streamer.py:113-132`
- `CRM-Client/src/views/AIAssistant.vue:handleSSEEvent`

---

## 下一步

需要添加诊断日志，运行一次，确认数据流：

```typescript
// 在 AIAssistant.vue handleSSEEvent 中添加：
console.log('[DIAG] SSE event:', event.event, event)

// 在 useAgentExecutionLog.ts handleToolCall 中添加：
console.log('[DIAG] tool_call step:', step)

// 在 AgentExecutionLog.vue 渲染时添加：
console.log('[DIAG] rendering step:', step)
```

---

## 修复计划

按照优先级：

| 优先级 | 问题 | 修复位置 |
|--------|------|----------|
| P0 | 工具名称未业务化 | `agentExecution.ts` ToolTitleMap |
| P1 | ThinkingBubble/业务参数重复 | `AgentExecutionLog.vue` 渲染条件 |
| P1 | 缺少 AI 思考过程 | `sse_streamer.py` + `useAgentExecutionLog.ts` |
| P2 | AI 回复重复 | `AIAssistant.vue` handleSSEEvent |