---
status: active
created: 2026-06-26
updated: 2026-07-03
version: 3.1
architecture: LangGraph v1.0
related_docs:
  - ../plans/AI-HUMAN-IN-THE-LOOP-DESIGN.md
  - ../requirements/AI-ASSISTANT-PAGE-REQUIREMENTS.md
---

# AI Agent 技术架构

> **版本：3.1 | LangGraph v1.0 架构**
> **更新日期：2026-07-03**
> **状态：生产可用 ✅**

---

## 一、功能概览

### 1.1 核心能力

AI Agent 是 CRMWolf 的智能助手，具备以下核心能力：

| 能力 | 说明 |
|------|------|
| **意图识别** | 解析用户输入，识别操作意图（创建、跟进、查询、状态变更） |
| **工具调用** | 17+ 个业务工具（线索、客户、商机、合同等） |
| **多轮对话** | ReAct 循环，AI 自主判断是否需要继续操作 |
| **流程编排** | Workflow 硬编码流程（赢单、转化等关键业务场景） |
| **人机协同** | 关键决策前询问用户确认（Human-in-the-Loop） |
| **安全控制** | Guardrails 护栏、置信度拦截、异常处理 |
| **状态持久化** | Redis Checkpointer，会话 30 分钟 TTL |

### 1.2 架构演进历史

| 版本 | 架构 | 时间 | 说明 |
|------|------|------|------|
| v1.0 | 单工具模式 | 2026-04 | 基础 AI 工具调用 |
| v2.0 | ReAct + Workflow + Control Plane | 2026-05 | 三层架构，Phase A-G 完成 |
| v3.0 | LangGraph StateGraph | 2026-06 | LangGraph 编排引擎，Redis Checkpointer |

### 1.3 三层架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                        用户输入                              │
│   "微信跟进客户，客户反馈产品适用，确认采购..."               │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                  Layer 1: LangGraph StateGraph               │
│   ┌─────────────────────────────────────────────────────┐   │
│   │  Router → IntentDetector → EntityResolver           │   │
│   │  → Preview → Confirm → Execute → End                │   │
│   │                                                      │   │
│   │  ReAct 循环：Execute → IntentDetector (继续判断)    │   │
│   │  Workflow 模式：硬编码业务流程编排                   │   │
│   └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                Layer 2: Control Plane                        │
│   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│   │ Redis       │  │ Guardrails  │  │ TraceId     │         │
│   │ Checkpointer│  │ 置信度拦截  │  │ 全链路追踪  │         │
│   │ TTL 30min   │  │             │  │             │         │
│   └─────────────┘  └─────────────┘  └─────────────┘         │
│   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│   │ Resource    │  │ Rate        │  │ Undo        │         │
│   │ Isolation   │  │ Limit       │  │ Service     │         │
│   └─────────────┘  └─────────────┘  └─────────────┘         │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                       Handler 执行                           │
│   CreateHandler, FollowUpHandler, StatusChangeHandler...    │
│   17+ 业务工具通过 HandlerFactory 路由                      │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                       SSE 事件流                             │
│   start → node_start → tool_call → tool_result              │
│   waiting_for_user → react_complete → workflow_complete     │
│   SSE Wrapper 转换 LangGraph astream_events                 │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                       前端交互                               │
│   AIAssistant.vue + AgentExecutionLog + InlinePill          │
│   aiConversation Store（Pinia 状态管理）                    │
└─────────────────────────────────────────────────────────────┘
```

### 1.4 配置开关矩阵

| 配置项 | 默认值 | 说明 | 位置 |
|--------|--------|------|------|
| `AGENT_ENABLED` | `False` | Agent 模式总开关 | `config.py` |
| `REACT_ENABLED` | `True` | ReAct 循环开关（已稳定） | `config.py` |
| `WORKFLOW_ENABLED` | `True` | Workflow 模式开关 | `config.py` |
| `MULTI_TOOL_ENABLED` | `True` | 多工具返回开关 | `config.py` |
| `REACT_MAX_ROUNDS` | `10` | ReAct 最大轮数 | `config.py` |
| `AGENT_TIMEOUT` | `120` | Agent 执行超时（秒） | `config.py` |
| `AGENT_SESSION_TIMEOUT` | `1800` | 会话过期时间（30min） | `config.py` |
| `AGENT_THREAD_POOL_SIZE` | `4` | Agent 专用线程池 | `config.py` |
| `AGENT_MAX_CONCURRENT` | `10` | 最大并发数 | `config.py` |
| `AGENT_USER_RATE_LIMIT` | `10` | 用户速率限制（次/分钟） | `config.py` |
| `LANGCHAIN_TRACING_V2` | `True` | LangSmith Tracing 开关 | `config.py` |

---

## 二、Layer 1: LangGraph StateGraph（编排引擎）

### 2.1 核心架构

**位置**：`CRM-Server/app/services/langgraph/`

| 组件 | 文件 | 职责 |
|------|------|------|
| **AgentState** | `state.py` | TypedDict 状态定义（JSON-serializable） |
| **Checkpointer** | `checkpointer.py` | Redis 持久化（TTL 30min） |
| **SSE Wrapper** | `sse_wrapper.py` | LangGraph → CRMWolf SSE 格式转换 |
| **Nodes** | `nodes/intent.py` | Router、Intent、Entity、Preview、Execute 等 |

### 2.2 AgentState 状态定义

```typescript
interface AgentState {
  // Message History（OpenAI 格式）
  messages: Message[]  // add_messages reducer 自动合并

  // Session Context
  session_id: string
  user_id: number
  team_id: number

  // Entity Context（当前聚焦实体）
  entity_context: {
    entity_type: string    // "customer" | "opportunity" | "lead"
    entity_id: number
    entity_name: string
  } | null

  // Execution State
  round_num: number       // ReAct 循环轮数
  execution_history: ExecutionRecord[]  // 执行历史审计
}
```

**关键设计**：
- 所有字段必须 JSON-serializable（Redis Checkpointer 要求）
- `db` 和 `user` 通过 `config["configurable"]` 传递，不存储在状态中
- `messages` 使用 LangGraph 的 `add_messages` reducer 自动合并

### 2.3 Graph 流程图

```
┌─────────────────────────────────────────────────────────────┐
│                         START                                │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                        Router                                │
│   - 关键词匹配："确认采购" → workflow: customer_win_flow    │
│   - 或 → intent_detector (ReAct 模式)                       │
└─────────────────────────────────────────────────────────────┘
                              ↓
        ┌─────────────────────┴─────────────────────┐
        ↓                                           ↓
┌───────────────────┐                   ┌───────────────────┐
│  Workflow 模式    │                   │   ReAct 循环      │
│  (业务流程编排)    │                   │  (AI 自主判断)    │
│                   │                   │                   │
│ customer_win_flow │                   │  IntentDetector   │
│ lead_convert_flow │                   │  → EntityResolver │
│                   │                   │  → Preview        │
│ Step: tool        │                   │  → Confirm        │
│ Step: ask_user    │                   │  → Execute        │
│ Step: decision    │                   │  → (ReAct 循环)   │
└───────────────────┘                   └───────────────────┘
        │                                           │
        └─────────────────────┬─────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                     Human-in-the-Loop                        │
│   waiting_for_user → 用户确认 → continue                     │
│   waiting_for_user → 用户取消 → rollback                     │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                          END                                 │
└─────────────────────────────────────────────────────────────┘
```

### 2.4 Node 类型与职责

| Node | 职责 | 输入 | 输出 |
|------|------|------|------|
| **Router** | 路由决策：Workflow vs ReAct | messages | 路由目标 |
| **IntentDetector** | 意图识别 + 工具选择 | messages, entity_context | tool_calls |
| **EntityResolver** | 实体解析 +歧义消解 | entity_name, entity_type | entity_context |
| **Preview** | 参数预览 + 校验 | tool_calls, entity_context | preview_data |
| **Confirm** | Human-in-the-Loop 确认 | preview_data | user_response |
| **Execute** | 工具执行 + 结果处理 | tool_calls, user_response | execution_result |

### 2.5 ReAct 循环机制

**核心逻辑**：

```
用户输入 → AI 解析 → tool_calls → 执行 → tool_result → AI 判断 → 继续或完成
```

**关键改动（v2.0 vs v1.0）**：

| 改动点 | v1.0 | v2.0/v3.0 |
|--------|------|-----------|
| 每轮暂停 | ❌ 全部暂停等待确认 | ✅ 只有 `ask_user` 暂停 |
| 消息格式 | ❌ 不符合标准 | ✅ OpenAI 标准格式 |
| 上下文注入 | ❌ 循环中缺失 | ✅ 第一轮自动注入 |
| AI 自主判断 | ❌ 硆编码分析 | ✅ AI 根据结果自主判断 |

---

## 三、Layer 2: Workflow Orchestrator（业务编排层）

### 3.1 已实现流程

| 流程 | 触发关键词 | 步骤序列 | 文件 |
|------|----------|----------|------|
| `customer_win_flow` | 确认采购、已签约、赢单 | 跟进 → 获取商机 → 选择/确认 → 赢单 → 创建合同 | `workflow_definitions.py` |
| `lead_convert_flow` | 转客户、转化 | 跟进 → 检查状态 → 确认转化 → 创建客户+商机 | `workflow_definitions.py` |

### 3.2 Workflow 步骤类型

| 类型 | 是否自动执行 | 说明 | 示例 |
|------|-------------|------|------|
| `tool` | ✅ 自动执行 | 低风险操作 | `create_follow_up`, `get_entity_context` |
| `ask_user` | ❌ 需要确认 | 关键决策 | `ask_confirm_win_single` |
| `decision` | ✅ 条件判断 | 流程分支 | `check_opportunity` |

### 3.3 状态机校验

```
商机：FOLLOWING → WON/LOST → (终态，不可逆)
线索：NEW → FOLLOWING → CONVERTED/INVALID → (终态)
合同：DRAFT → PENDING_REVIEW → SIGNED → EFFECTIVE → TERMINATED
```

**文件**：`CRM-Server/app/services/workflow/state_machine.py`

### 3.4 业务不变式

| 不变式 | 校验规则 | 文件 |
|--------|----------|------|
| `win_requires_opportunity` | 赢单前必须有商机 | `business_invariants.py` |
| `contract_requires_won_opportunity` | 合同必须关联已赢单商机 | `business_invariants.py` |
| `contract_amount_le_opportunity_amount` | 合同金额 ≤ 商机金额 | `business_invariants.py` |

---

## 四、Layer 3: Control Plane（系统控制层）

### 4.1 核心组件

| 组件 | 文件 | 功能 |
|------|------|------|
| **Redis Checkpointer** | `langgraph/checkpointer.py` | LangGraph 状态持久化，TTL 30min |
| **Guardrails** | `workflow/guardrails.py` | 置信度阈值拦截 + 异常分层 |
| **TraceId** | `workflow/trace_context.py` | 全链路追踪 + AI Decision Audit |
| **Resource Isolation** | `workflow/agent_executor_pool.py` | 独立线程池 + 并发限制 + 超时保护 |
| **Undo Service** | `workflow/undo_service.py` | 单步撤销 + 流程级撤销 |
| **Entity Renderer** | `workflow/entity_renderer.py` | 增强型实体展示（金额、阶段等） |

### 4.2 Redis Checkpointer（v3.0 新增）

**Key 格式**：`langgraph:checkpoint:{thread_id}`

**特性**：
- TTL 30 分钟自动过期
- 兼容 LangGraph Checkpointer 接口
- 支持 `astream_events` 异步流

**使用示例**：

```python
checkpointer = RedisCheckpointer(
    redis_url="redis://localhost:6379",
    ttl=1800  # 30 minutes
)

app = graph.compile(checkpointer=checkpointer)

# 异步流式执行
async for event in app.astream_events(inputs, thread_id):
    yield sse_wrapper.convert(event)
```

### 4.3 Guardrails 置信度拦截

| 置信度阈值 | 行为 |
|-----------|------|
| ≥ 0.95 | 直接执行（高风险操作仍需确认） |
| ≥ 0.80 | 执行但记录审计日志 |
| ≥ 0.70 | 提示用户确认 |
| < 0.70 | 拒绝执行，要求用户明确指令 |

### 4.4 撤销机制（Phase F）

| 功能 | 文件 | 说明 |
|------|------|------|
| Undo Service | `undo_service.py` | 单步撤销 + 流程级撤销 |
| Undo Handlers | `undo_handlers.py` | 6 种操作类型撤销处理器 |
| Entity Renderer | `entity_renderer.py` | 商机/客户展示金额、阶段等 |
| Undo API | `api/workflow_undo.py` | `/workflow/undo` REST API |

**撤销窗口配置**：

| 操作类型 | TTL | 撤销范围 |
|----------|-----|----------|
| 创建跟进记录 | 10秒 | 单步撤销 |
| 赢单 | 30秒 | 流程撤销 |
| 线索转化 | 60秒 | 流程撤销 |

### 4.5 资源隔离机制

```
独立线程池：AGENT_THREAD_POOL_SIZE = 4
并发限制：AGENT_MAX_CONCURRENT = 10
超时保护：AGENT_TIMEOUT = 120s
速率限制：10 次/分钟（用户级），100 次/分钟（全局）
```

---

## 五、前端交互系统

### 5.1 组件架构

**位置**：`CRM-Client/src/components/`

```
AIAssistant.vue (独立页面)
├── Header
│   ├── ToggleSidebar 按钮
│   └── NewConversation 按钮
├── Sidebar (HistoryList)
│   ├── Today 分组
│   ├── Yesterday 分组
│   └── Earlier 分组
└── Conversation Area
    ├── MessageList
    │   ├── UserMessage
    │   └── AssistantMessage
    │       └── AgentExecutionLog (执行轨迹)
    │           ├── InlineStep (步骤节点)
    │           ├── InlineCandidate (候选选择)
    │           └── InlinePill (确认胶囊)
    │       └── WorkflowProgress (工作流进度)
    │           └── WorkflowMiniMap (流程 Mini-map)
    └── InputArea
        └── TextInput + SubmitButton
    └── UndoToast (底部撤销提示)
```

### 5.2 核心组件清单

| 组件 | 文件 | 行数 | 说明 |
|------|------|------|------|
| **AIAssistant.vue** | `views/AIAssistant.vue` | 700+ | 独立页面主入口 |
| **AgentExecutionLog** | `components/AgentExecutionLog.vue` | 100+ | 执行轨迹容器 |
| **InlineStep** | `components/InlineStep.vue` | 150+ | 步骤节点（思考/查询/执行） |
| **InlineCandidate** | `components/InlineCandidate.vue` | 100+ | 候选实体选择 |
| **InlinePill** | `components/InlinePill.vue` | 250+ | 确认胶囊（一行摘要 + 展开） |
| **WorkflowProgress** | `components/WorkflowProgress.vue` | 300+ | Workflow 进度条 |
| **WorkflowMiniMap** | `components/WorkflowMiniMap.vue` | 150+ | 流程进度 Mini-map |
| **UndoToast** | `components/UndoToast.vue` | 150+ | 底部撤销提示（倒计时） |

### 5.3 状态管理

**位置**：`CRM-Client/src/stores/aiConversation.ts`

```typescript
interface AIConversationState {
  // 历史对话列表（按日期分组）
  historyGroups: {
    today: Conversation[]
    yesterday: Conversation[]
    earlier: Conversation[]
  }

  // 当前对话（单一状态源）
  currentConversation: ConversationDetail | null
  currentId: string | null

  // 消息列表
  messages: Message[]

  // 执行步骤（与 API ExecutionStep 对齐）
  executionSteps: ExecutionStep[]
}
```

**核心方法**：
- `loadHistory()` - 加载历史对话列表
- `loadConversation(id)` - 加载对话详情（刷新恢复）
- `saveConversation()` - 实时保存对话
- `handleSSEEvent()` - SSE 事件处理

### 5.4 Inline 交互模式

**设计理念**：
- **Inline Pill**：默认一行摘要，点击展开详情
- **Inline Candidate**：候选实体单行展示，Hover Tooltip 详情
- **Inline Step**：步骤节点紧凑显示，进度可视化

**交互流程**：

```
1. 用户输入 → SSE stream
2. node_start → InlineStep 显示
3. tool_call → InlineStep 更新（执行态）
4. tool_result → InlineStep 完成（结果态）
5. waiting_for_user → InlinePill 显示（确认态）
6. 用户确认 → continue → 执行
7. undo_available → UndoToast 显示（倒计时）
```

---

## 六、前后端通信协议

### 6.1 SSE 事件类型

| 事件类型 | 说明 | 数据结构 |
|----------|------|----------|
| `start` | Session 开始 | `{ session_id }` |
| `node_start` | Node 执行开始 | `{ node_name, input }` |
| `node_result` | Node 执行结果 | `{ node_name, output }` |
| `tool_call` | 工具调用开始 | `{ tool_name, params }` |
| `tool_result` | 工具执行结果 | `{ tool_name, result, success }` |
| `waiting_for_user` | Human-in-the-Loop | `{ question, options, undo_config }` |
| `react_complete` | ReAct 循环完成 | `{ rounds, summary }` |
| `workflow_complete` | Workflow 完成 | `{ workflow_id, steps_results }` |
| `undo_available` | 撤销可用 | `{ operation_id, undo_ttl, undo_endpoint }` |
| `error` | 错误 | `{ error_type, message, trace_id }` |

### 6.2 API 接口定义

| 端点 | 方法 | 说明 |
|------|------|------|
| `/v1/customers/ai/parse` | POST | AI 解析客户跟进（SSE 流式） |
| `/v1/customers/ai/create` | POST | 创建跟进记录（用户确认后） |
| `/v1/assistant/chat` | POST | LangGraph 主对话入口 |
| `/v1/assistant/workflow/continue` | POST | Human-in-the-Loop 恢复 |
| `/v1/assistant/session/{id}` | GET | 查询 Session 状态 |
| `/v1/assistant/session/{id}` | DELETE | 取消 Session |
| `/v1/workflow/undo/{operation_id}` | POST | 单步撤销 |
| `/v1/workflow/undo/workflow/{session_id}` | POST | 流程级撤销 |
| `/v1/ai/conversations` | GET | 历史对话列表 |
| `/v1/ai/conversations/{id}` | GET | 对话详情 |
| `/v1/ai/conversations` | POST | 创建新对话 |
| `/v1/ai/conversations/{id}` | DELETE | 删除对话 |
| `/v1/approval-ai/parse` | POST | AI 审批流程解析（支持 business_type 识别：回款→PAYMENT / 发票→INVOICE / 合同→CONTRACT） |
| `/v1/approval-ai/create` | POST | 解析结果落库为审批流程 |

### 6.2.1 AI 审批流解析器（business_type 识别，Task B3）

**位置**：`CRM-Server/app/services/approval_ai_parser.py`

AI 审批流解析器（ApprovalAIParserService）在 Task B3 中扩展为支持 `business_type` 识别，使用户可用自然语言为不同单据类型创建审批流程。

**识别规则**（输出 `business_type` 字段，schema 层缺失/非法回退 CONTRACT）：

| 用户描述关键词 | business_type | 说明 |
|----------------|---------------|------|
| 回款 / 收款 / 入账 / 回款登记 | `PAYMENT` | 回款类审批流程 |
| 发票 / 开票 / 发票申请 / 增值税发票 | `INVOICE` | 发票类审批流程 |
| 合同 / 签约 / 协议 / 未明确 | `CONTRACT` | 合同类审批流程（默认） |

**关键约束**：
1. 按用户描述的**单据类型**（而非审批角色，如"财务审批"）判定 `business_type`
2. `business_type` 必须是 CONTRACT / PAYMENT / INVOICE 之一
3. schema 校验器对缺失/非法值回退 CONTRACT
4. 解析结果落库时由 `/v1/approval-ai/create` 写入 `ApprovalFlow.business_type`

**与审批引擎的关系**：解析器只负责生成 `ApprovalFlow` 定义；运行时由通用审批 API `/v1/approvals/{entity_type}/{id}/...` 按 `business_type` 匹配流程（参见决策1：未配置流程，CONTRACT 报错、PAYMENT/INVOICE 免审批直通）。

### 6.3 SSE Wrapper 转换逻辑

**位置**：`CRM-Server/app/services/langgraph/sse_wrapper.py`

```python
async def stream_sse_events(app, inputs, thread_id):
    """LangGraph astream_events → CRMWolf SSE 格式"""

    async for event in app.astream_events(inputs, thread_id):
        # LangGraph event types:
        # - on_chain_start → node_start
        # - on_chain_end → node_result
        # - on_tool_start → tool_call
        # - on_tool_end → tool_result

        sse_event = convert_langgraph_event(event)
        yield f"data: {json.dumps(sse_event)}\n\n"
```

---

## 七、Handler 系统

### 7.1 Handler 清单

**位置**：`CRM-Server/app/services/skills/handlers/`

| Handler | 文件 | 行数 | 职责 |
|---------|------|------|------|
| **BaseHandler** | `base_handler.py` | 300+ | Handler 基类（快照、撤销日志） |
| **CreateHandler** | `create_handler.py` | 800+ | 创建客户、商机、线索 |
| **FollowUpHandler** | `follow_up_handler.py` | 400+ | 创建跟进记录 |
| **StatusChangeHandler** | `status_change_handler.py` | 600+ | 赢单/输单、线索转化 |
| **StageAdvanceHandler** | `stage_advance_handler.py` | 500+ | 推进商机阶段 |
| **QueryListHandler** | `query_list_handler.py` | 150+ | 查询实体列表 |
| **QueryDetailHandler** | `query_detail_handler.py` | 250+ | 查询实体详情 |
| **GetContextHandler** | `get_context_handler.py` | 700+ | 获取实体上下文 |
| **AskUserHandler** | `ask_user_handler.py` | 100+ | 人机协同询问 |
| **LeadConvertHandler** | `lead_convert_handler.py` | 170+ | 线索转化 |
| **SetNextFollowHandler** | `set_next_follow_handler.py` | 130+ | 设置下次跟进 |
| **SetProcurementMethodHandler** | `set_procurement_method_handler.py` | 400+ | 设置采购方式 |
| **AggregateHandler** | `aggregate_handler.py` | 220+ | 聚合操作 |

### 7.2 Handler 工厂模式

**位置**：`CRM-Server/app/services/skills/handlers/handler_factory.py`

```python
class HandlerFactory:
    """Handler 路由工厂"""

    HANDLER_MAP = {
        "create_customer": CreateHandler,
        "follow_up_customer": FollowUpHandler,
        "win_opportunity": StatusChangeHandler,
        "advance_stage": StageAdvanceHandler,
        "query_list": QueryListHandler,
        "get_entity_context": GetContextHandler,
        "ask_user": AskUserHandler,
        # ... 17+ 工具映射
    }

    def get_handler(self, tool_name: str) -> BaseHandler:
        return self.HANDLER_MAP.get(tool_name)
```

### 7.3 Handler 撤销支持

**BaseHandler 方法**：

```python
class BaseHandler:
    def capture_snapshot(self, entity) -> Dict:
        """捕获实体快照"""
        ...

    def log_with_undo(self, db, result, undo_config):
        """记录操作日志（含撤销配置）"""
        ...
```

---

## 八、实施清单

### 8.1 后端文件清单

**新增文件**：

| 文件 | 说明 |
|------|------|
| `app/services/langgraph/state.py` | AgentState 定义 |
| `app/services/langgraph/checkpointer.py` | Redis Checkpointer |
| `app/services/langgraph/sse_wrapper.py` | SSE 事件转换 |
| `app/services/langgraph/nodes/intent.py` | Intent Node |
| `app/services/workflow/workflow_definitions.py` | 业务流程定义 |
| `app/services/workflow/state_machine.py` | 状态机校验 |
| `app/services/workflow/business_invariants.py` | 业务不变式 |
| `app/services/workflow/guardrails.py` | Guardrails 护栏 |
| `app/services/workflow/trace_context.py` | 全链路追踪 |
| `app/services/workflow/agent_executor_pool.py` | 资源隔离 |
| `app/services/workflow/undo_service.py` | 撤销服务 |
| `app/services/workflow/undo_handlers.py` | 撤销处理器 |
| `app/services/workflow/entity_renderer.py` | 实体展示渲染 |
| `app/services/skills/handlers/ask_user_handler.py` | ask_user Handler |
| `app/services/skills/handlers/get_context_handler.py` | get_entity_context Handler |
| `app/api/workflow_undo.py` | Undo API |
| `app/api/ai_conversation_history.py` | 对话历史 API |

**删除文件（v3.0）**：

| 文件 | 替代方案 |
|------|----------|
| `app/services/workflow/workflow_orchestrator.py` | LangGraph StateGraph |
| `app/services/workflow/session_store.py` | Redis Checkpointer |
| `app/services/ai_tool_service.py` | LangGraph nodes |

### 8.2 前端文件清单

| 文件 | 说明 |
|------|------|
| `views/AIAssistant.vue` | 独立页面 |
| `components/AgentExecutionLog.vue` | 执行轨迹 |
| `components/InlineStep.vue` | 步骤节点 |
| `components/InlineCandidate.vue` | 候选选择 |
| `components/InlinePill.vue` | 确认胶囊 |
| `components/WorkflowProgress.vue` | Workflow 进度 |
| `components/WorkflowMiniMap.vue` | 流程 Mini-map |
| `components/UndoToast.vue` | 撤销提示 |
| `components/MagicWandDialog.vue` | Drawer 入口（保留兼容） |
| `stores/aiConversation.ts` | Pinia Store |
| `api/aiConversation.ts` | API 接口 |
| `api/workflow.ts` | Workflow API |

### 8.3 测试覆盖率

| Phase | 测试数 | 通过率 |
|-------|--------|--------|
| Phase A（Redis Session） | 7 | 100% |
| Phase B（幂等恢复） | 5 | 100% |
| Phase C（Guardrails） | 6 | 100% |
| Phase D（TraceId） | 7 | 100% |
| Phase E（资源隔离） | 7 | 100% |
| **总计** | **32** | **100%** |

---

## 九、配置与部署

### 9.1 配置项清单

```python
# AI 工具配置
MULTI_TOOL_ENABLED: bool = True     # 多工具返回
REACT_ENABLED: bool = True          # ReAct 循环（已稳定）
AGENT_ENABLED: bool = False         # Agent 总开关（关闭）
WORKFLOW_ENABLED: bool = True       # Workflow 模式

# ReAct 循环
REACT_MAX_ROUNDS: int = 10          # 最大轮数
REACT_SINGLE_ROUND_TIMEOUT: int = 30
REACT_TOTAL_TIMEOUT: int = 120

# Session 管理
AGENT_SESSION_TIMEOUT: int = 1800   # 30min
WORKFLOW_SESSION_TIMEOUT: int = 1800

# 资源隔离
AGENT_THREAD_POOL_SIZE: int = 4
AGENT_MAX_CONCURRENT: int = 10
AGENT_TIMEOUT: int = 120
AGENT_USER_RATE_LIMIT: int = 10
AGENT_GLOBAL_RATE_LIMIT: int = 100

# LangSmith Tracing（调试）
LANGCHAIN_TRACING_V2: bool = True
LANGCHAIN_PROJECT: str = "CRMWolf-AI-Assistant"
```

### 9.2 部署检查清单

| 检查项 | 要求 |
|--------|------|
| Redis 服务 | 运行中，端口 6379 |
| LangSmith API Key | 已配置（可选，调试用） |
| 数据库迁移 | `alembic upgrade head` |
| Operation Log 表 | 包含撤销字段 |
| 测试覆盖率 | ≥ 90% |

### 9.3 监控指标建议

| 指标 | 说明 |
|------|------|
| `agent_rounds_avg` | ReAct 平均轮数 |
| `ask_user_rate` | 人机协同触发率 |
| `tool_success_rate` | 工具执行成功率 |
| `session_timeout_rate` | 会话超时率 |
| `guardrails_reject_rate` | Guardrails 拒绝率 |
| `undo_success_rate` | 撤销成功率 |
| `sse_latency_p99` | SSE 响应延迟 |

---

## 十、常见场景示例

### 10.1 场景 1：客户确认采购（无商机）

```
用户输入："客户确认采购"

Workflow 流程：
1. 自动创建跟进记录 ✅
2. 查询商机列表 → 发现无商机
3. 询问："是否创建商机？"
   - 用户回复："是，XX软件，50万"
4. 创建商机 ✅
5. 询问："是否标记赢单？"
   - 用户回复："是"
6. 标记赢单 ✅
7. 询问："是否创建合同？"
   - 用户回复："是"
8. 创建合同草稿 ✅
```

### 10.2 场景 2：客户确认采购（单个商机）

```
用户输入："微信跟进客户，客户确认采购"

Workflow 流程：
1. 自动创建跟进记录 ✅
2. 查询商机列表 → 发现1个商机
3. InlinePill 显示："是否标记商机「XX」为赢单？"
   - 用户点击"确认"
4. 推进到最终阶段 + 标记赢单 ✅
5. UndoToast 显示："操作完成，30秒内可撤销"
```

### 10.3 场景 3：普通跟进

```
用户输入："电话联系了客户张三"

ReAct 流程：
1. IntentDetector → follow_up_customer
2. EntityResolver → 客户张三（ID: 101）
3. Preview → 参数预览
4. InlinePill 显示："创建跟进记录 · 张三"
   - 用户点击"确认"
5. 创建跟进记录 ✅
6. UndoToast 显示："跟进记录已创建，10秒内可撤销"
```

---

## 附录

### A. 相关文档链接

| 文档 | 路径 | 说明 |
|------|------|------|
| **人机协同设计** | `CRM-Docs/plans/AI-HUMAN-IN-THE-LOOP-DESIGN.md` | UI/UX 设计规范 V2 |
| **独立页面需求** | `CRM-Docs/requirements/AI-ASSISTANT-PAGE-REQUIREMENTS.md` | 页面功能需求 |
| **执行日志需求** | `CRM-Docs/requirements/AI-ASSISTANT-EXECUTION-LOG-REQUIREMENTS.md` | 执行轨迹需求 |
| **撤销需求** | `CRM-Docs/archive/requirements/AI-AGENT-SAFETY-ENHANCEMENT-REQUIREMENTS.md` | 撤销机制需求（已实施） |
| **Inline 需求** | `CRM-Docs/archive/requirements/AI-AGENT-INLINE-INTERACTION-REQUIREMENTS.md` | Inline 交互需求（已实施） |

### B. 术语表

| 术语 | 说明 |
|------|------|
| **LangGraph** | LangChain 官方状态编排引擎，替代 workflow_orchestrator |
| **StateGraph** | LangGraph 的状态图，定义 Node 和 Edge |
| **Checkpointer** | LangGraph 状态持久化组件（Redis 实现） |
| **ReAct** | Reasoning + Acting 循环，AI 自主判断 |
| **Workflow** | 硬编码业务流程编排（赢单、转化） |
| **Human-in-the-Loop** | 人机协同，关键决策前询问用户 |
| **Guardrails** | 安全护栏，置信度拦截 |
| **Inline Pill** | 确认胶囊，一行摘要 + 点击展开 |
| **Undo Toast** | 撤销提示，底部倒计时 |

---

> **版本历史**：
> - v1.0（2026-04）：单工具模式
> - v2.0（2026-05）：ReAct + Workflow + Control Plane 三层架构
> - v3.0（2026-06）：LangGraph StateGraph + Redis Checkpointer
> - v3.1（2026-07）：AI 审批流解析器支持 business_type 识别（CONTRACT/PAYMENT/INVOICE，Task B3）

> **下一步**：持续优化 LangSmith Tracing、监控指标完善