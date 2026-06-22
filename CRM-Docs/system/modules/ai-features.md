---
priority: high
status: active
module_type: ai
---

# AI 功能模块文档

> 版本：2.1 | 更新日期：2026-06-12 | 状态：已实现
> 关联需求：`CRM-Docs/archive/requirements/AI-GLUE-REQUIREMENTS.md`
> 关联实现：`CRM-Docs/changelog/enhancements/2026-06-12-ai-agent-feature-summary.md`

---

## AI 交互意图

### AI 在此模块的核心任务

| 任务场景 | AI 操作意图 | 约束条件 | 风险等级 |
|----------|-------------|----------|----------|
| 意图识别 | 解析用户自然语言输入 | 关键词匹配 + Function Calling | P1 |
| 工具调用 | 执行业务工具（17+ 个） | Handler 映射、参数校验 | P0 |
| ReAct 循环 | 多轮对话、自主判断继续 | 最大轮数限制（10轮）、超时保护（120s） | P0 |
| Workflow 编排 | 关键业务流程（赢单、转化） | 状态机校验、业务不变式检查 | P0 |
| 人机协同 | 关键决策前询问确认 | ask_user 工具、用户响应处理 | P0 |
| 撤销保护 | 关键操作可撤销 | TTL 窗口（10-60秒）、撤销处理器 | P0 |

### AI 禁止行为

| 禁止行为 | 原因 | 替代方案 |
|----------|------|----------|
| ❌ 臆测工具参数 | 违反禁止臆测红线 | 必须通过 get_entity_context 获取上下文 |
| ❌ 赢单前没有商机 | 违反业务不变式 | 必须先确认商机存在 |
| ❌ 跨 team_id 操作 | 违反团队隔离红线 | 必须注入 team_id |
| ❌ 跳过用户确认执行高风险操作 | 违反人机协同规则 | 必须调用 ask_user |
| ❌ 低置信度直接执行 | 违反 Guardrails 规则 | 置信度 < 0.70 必须拒绝 |

### AI 配置开关

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `AGENT_ENABLED` | False | Agent 模式总开关 |
| `REACT_ENABLED` | False | ReAct 循环开关 |
| `WORKFLOW_ENABLED` | True | Workflow 编排开关 |
| `REACT_MAX_ROUNDS` | 10 | ReAct 最大轮数 |
| `AGENT_TIMEOUT` | 120 | 执行超时（秒） |

### AI 必查文档

| 场景 | 必查文档 | 查阅时机 |
|------|----------|----------|
| AI 接口开发 | `CRM-Docs/standards/AI-API-STANDARD.md` | 开发 AI 功能前 |
| 工具定义 | `CRM-Server/app/constants/tools.py` | 新增工具前 |
| Handler 实现 | `CRM-Server/app/services/skills/handlers/` | 实现 Handler 前 |
| 业务不变式 | `CRM-Server/app/services/workflow/business_invariants.py` | 赢单/转化前 |

---

## 一、模块概述（AI 功能定位）

### 1.1 功能定位

**AI 功能模块**是 CRMWolf 系统的智能交互层，提供自然语言驱动的业务操作能力，解决"口语表达 → 系统操作"的交互范式不匹配问题。

### 1.2 核心能力

| 能力 | 说明 |
|------|------|
| **自然语言理解** | 强依赖 LLM，支持口语表达（如"跟进张三客户"、"改成35万"） |
| **多意图分解** | 复合指令拆解（如"跟进张三并设置下周提醒" → 两个独立意图） |
| **实体消解** | 模糊引用 → 精确 ID（"那个客户"、"张三的商机"） |
| **歧义消解** | 多候选追问 + 描述性选择（"选谈判中的那个"） |
| **槽位收集** | 缺失字段多轮追问 |
| **预览确认** | 所有写操作 preview → 确认 → execute 安全闭环 |
| **ReAct 循环** | Agent 自主决策循环，支持复杂业务链路 |
| **Workflow 编排** | 预定义业务流程自动推进 |

### 1.3 架构合规

所有写操作通过 **入口函数层**（`ActionEntry`），满足：
- **Single Writer 原则**：唯一写入入口
- **Preview 单一 Truth 原则**：预览逻辑不重复
- **R-1~R-5 合规**：意图 → Action → CRUD 标准链路

---

## 二、功能架构（Intent/Action/Metadata 分层）

### 2.1 分层架构

```
┌─────────────────────────────────────────────────────────────┐
│                     前端交互层                               │
│  MagicWandDialog.vue / WorkflowProgress.vue                │
│  SSE 流式响应 + 实体上下文注入                              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   API 端点层                                │
│  /v1/assistant/chat (web_assistant.py)                     │
│  /v1/assistant/workflow/continue                           │
│  SSE 事件流：status/content/parsed/result/error            │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   AI 服务层                                 │
│  AIToolService (ai_tool_service.py)                        │
│  ├─ handle_message_stream: 单工具/多工具模式                │
│  ├─ _handle_message_with_react: ReAct 循环模式              │
│  └─ continue_workflow: Workflow 模式                       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Handler 层                                │
│  HandlerFactory → BaseHandler                              │
│  ├─ CreateHandler: 创建实体                                │
│  ├─ QueryListHandler: 查询列表                             │
│  ├─ QueryDetailHandler: 查询详情                           │
│  ├─ StatusChangeHandler: 状态变更                          │
│  ├─ FollowUpHandler: 创建跟进                              │
│  ├─ StageAdvanceHandler: 阶段推进                          │
│  ├─ AskUserHandler: 询问用户                               │
│  └─ GetContextHandler: 获取上下文                          │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   入口函数层                                │
│  ActionEntry (action_entry.py)                             │
│  ├─ 权限校验 + 业务校验                                    │
│  ├─ Preview 构造（单一 Truth）                              │
│  ├─ Execute 执行（调用 CRUD）                              │
│  └─ 审计留痕（source/action_id）                           │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   CRUD 层                                   │
│  CRUD 统一入口（app/crud/）                                 │
│  team_id 必传 + 租户隔离                                    │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 三种执行模式

| 模式 | 说明 | 配置开关 |
|------|------|---------|
| **单工具/多工具** | Function Calling 直接解析，parsed → 确认 → execute | `MULTI_TOOL_ENABLED` |
| **ReAct 循环** | Agent 自主决策循环，ask_user 暂停等待 | `REACT_ENABLED` |
| **Workflow 编排** | 预定义业务流程（如"客户确认采购 → 赢单 → 创建合同"） | `WORKFLOW_ENABLED` |

### 2.3 ReAct 循环机制

```
用户输入 → [Think: 调用 AI] → [Act: 工具调用]
    ↓
ask_user? → 暂停循环，等待用户回复
    ↓
普通工具? → 执行 → 自动继续下一轮
    ↓
AI 返回文本? → 完成，输出结果
```

**关键特性**：
- 只有 `ask_user` 才暂停循环
- 普通工具执行后自动继续
- AI 自主判断是否需要继续（不硬编码分析提示词）
- 消息格式符合 OpenAI 标准：`assistant(tool_calls) → tool(result)`

---

## 三、核心功能

### 3.1 Function Calling 工具定义

**文件路径**：`app/constants/tools.py`

**工具分类**：

| 分类 | 工具数量 | 示例 |
|------|---------|------|
| 线索管理 | 9 | `create_lead`, `query_leads`, `follow_up_lead`, `convert_lead` |
| 客户管理 | 4 | `create_customer`, `query_customers`, `follow_up_customer` |
| 商机管理 | 7 | `create_opportunity`, `query_opportunities`, `win_opportunity`, `lose_opportunity` |
| 合同管理 | 4 | `create_contract`, `query_contracts`, `update_contract_status` |
| 回款管理 | 4 | `create_payment_plan`, `create_payment_record`, `confirm_payment` |
| 发票管理 | 3 | `create_invoice_application`, `query_invoice_applications` |
| 通用操作 | 2 | `set_next_follow_time`, `get_sales_funnel` |
| Agent 核心 | 2 | `ask_user`, `get_entity_context` |

**工具 Schema 格式**（OpenAI Function Calling）：

```json
{
  "type": "function",
  "function": {
    "name": "create_lead",
    "description": "创建新的销售线索",
    "parameters": {
      "type": "object",
      "properties": {
        "lead_name": {"type": "string", "description": "线索名称"},
        "contact_phone": {"type": "string", "description": "联系电话"}
      },
      "required": ["lead_name", "contact_phone"]
    }
  }
}
```

### 3.2 Handler 配置映射

**文件路径**：`app/constants/handler_configs.py`

**Handler 类型**：

| Handler | 职责 | 示例工具 |
|---------|------|---------|
| `CreateHandler` | 创建实体 | `create_lead`, `create_customer`, `create_opportunity` |
| `QueryListHandler` | 查询列表 | `query_leads`, `query_customers`, `query_opportunities` |
| `QueryDetailHandler` | 查询详情 | `get_lead_detail`, `get_customer_detail` |
| `StatusChangeHandler` | 状态变更 | `assign_lead`, `win_opportunity`, `lose_opportunity` |
| `FollowUpHandler` | 创建跟进 | `follow_up_lead`, `follow_up_customer` |
| `StageAdvanceHandler` | 阶段推进 | `advance_opportunity_stage` |
| `AskUserHandler` | 询问用户 | `ask_user`（暂停循环） |
| `GetContextHandler` | 获取上下文 | `get_entity_context`（返回实体完整信息） |

### 3.3 实体上下文注入

**触发条件**：用户在实体详情页操作时，前端传递 `entity_context`。

**格式**：
```json
{
  "entity_type": "customer",
  "entity_id": 10,
  "entity_name": "某某公司"
}
```

**自动注入逻辑**：
- 上下文是客户 → 自动填充 `customer_name`、`customer_id`
- 上下文是商机 → 自动填充 `opportunity_name`、`opportunity_id`
- 上下文是线索 → 自动填充 `lead_name`、`lead_id`
- 上下文是合同 → 自动填充 `contract_name`、`contract_id`

**实现位置**：`ai_tool_service.py` → `_inject_context_to_params`

### 3.4 会话上下文管理

**Session 存储**（内存 + Redis）：

| 字段 | 说明 |
|------|------|
| `entity_context` | 当前操作实体 |
| `entity_summary` | 实体完整信息汇总 |
| `related_entities` | 关联实体列表（商机列表等） |
| `executed_tools` | 已执行的工具列表 |
| `messages` | ReAct 循环消息历史 |

**关键方法**：
- `_save_react_session`: 保存 ReAct 会话状态
- `_load_react_session`: 加载 ReAct 会话状态（支持过期检查）
- `_inject_from_session_context`: 从会话上下文注入参数

---

## 四、数据模型（关键 Schema）

### 4.1 SSE 事件类型

| 事件 | 说明 | 返回字段 |
|------|------|---------|
| `status` | 状态更新 | `message` |
| `content` | AI 思考片段 | `content` |
| `parsed` | 单工具解析完成 | `tool`, `params`, `param_definitions`, `missing_params` |
| `parsed_multi` | 多工具解析完成 | `tool_calls`（数组） |
| `tool_call` | 工具调用开始 | `tool`, `params` |
| `tool_result` | 工具执行结果 | `tool`, `result` |
| `result` | 最终结果 | `message`, `data` |
| `error` | 错误信息 | `message` |
| `waiting_for_user` | 等待用户回复 | `question`, `options`, `missing_fields`, `field_options` |
| `react_start` | ReAct 循环开始 | `max_rounds`, `session_id` |
| `react_complete` | ReAct 循环完成 | `rounds` |
| `workflow_start` | Workflow 流程启动 | `workflow_id` |
| `workflow_complete` | Workflow 流程完成 | `workflow_id` |

### 4.2 UserExecCtx（用户执行上下文）

**文件路径**：`app/services/ai/action_entry.py`

**定义**：
```python
@dataclass
class UserExecCtx:
    user_id: int               # 用户 ID
    tenant_id: int             # 租户/团队 ID
    roles: List[str]           # 用户角色列表
    is_ai: bool = False        # 是否为 AI 调用
    source: str = "web"        # 调用来源 ("web" | "ai" | "glue")
    user_name: Optional[str] = None  # 用户名称（审计用）
```

**设计原则**：
- 替代裸 `db: Session` 参数
- 调用方（HTTP adapter、glue executor）通过此上下文传递用户信息
- ActionEntry 内部管理 db Session

### 4.3 ActionEntryResult（入口函数返回类型）

```python
@dataclass
class ActionEntryResult:
    action_id: str              # 动作唯一标识
    status: str                 # "preview" | "completed" | "failed"
    plan: Optional[ActionPlan]  # preview 态
    data: Optional[Dict]        # execute 态
    error: Optional[str]        # 错误信息
    requires_confirmation: bool # 是否需要确认
    confidence: float           # 置信度
```

### 4.4 ActionPlan（预览计划）

```python
@dataclass
class ActionPlan:
    description: str            # 操作描述
    changes: List[FieldChange]  # 字段变更列表
    entity_type: str            # 实体类型
    entity_id: Optional[int]    # 实体 ID
```

---

## 五、API 接口清单

### 5.1 Web AI 助手接口

**文件路径**：`app/api/web_assistant.py`

| 接口 | 方法 | 说明 |
|------|------|------|
| `/v1/assistant/chat` | POST | AI 助手聊天（SSE 流式响应） |
| `/v1/assistant/workflow/continue` | POST | 用户回复后继续 Workflow 流程 |

**请求格式**：

```json
{
  "content": "跟进张三客户",
  "entity_context": {
    "entity_type": "customer",
    "entity_id": 10,
    "entity_name": "某某公司"
  },
  "tool": null,         // 确认执行时填写
  "params": null        // 确认执行时填写
}
```

### 5.2 其他 AI API

**文件路径**：`app/api/`

| 文件 | 说明 |
|------|------|
| `customer_ai.py` | 客户模块 AI 接口 |
| `lead_ai.py` | 线索模块 AI 接口 |
| `procurement_ai.py` | 采购流程 AI 接口 |
| `ai_config.py` | AI 配置管理接口 |
| `ai_skills.py` | AI Skill 定义接口 |

---

## 六、前端页面

### 6.1 MagicWandDialog.vue

**文件路径**：`CRM-Client/src/components/MagicWandDialog.vue`

**功能**：
- AI 助手对话界面
- SSE 流式响应展示
- 实体上下文自动注入
- 多工具确认界面
- 歧义消解选择界面

**关键组件**：
- `AgentProgress.vue`: Agent 进度展示
- `ConfirmationCard.vue`: 操作确认卡片
- `EntitySelectDialog.vue`: 实体选择对话框
- `UndoToast.vue`: 操作撤销提示

### 6.2 WorkflowProgress.vue

**文件路径**：`CRM-Client/src/components/WorkflowProgress.vue`

**功能**：
- Workflow 流程进度展示
- 步骤执行状态可视化
- Mini Map 导航

---

## 七、业务规则

### 7.1 Preview 模式

**触发条件**：所有写操作（创建、状态变更、金额更新等）。

**流程**：
1. ActionEntry 入口函数 → Preview 态返回 `ActionPlan`
2. 前端展示预览内容（字段变更摘要）
3. 用户确认 → Execute 态执行

**风险分级**：
- **LOW**: 低风险操作（创建跟进、查询） → 无需强制确认
- **HIGH**: 高风险操作（赢单、输单） → 强制确认

**配置位置**：`app/constants/ai_rules.py`

### 7.2 幂等性保证

**机制**：
- `action_id` 统一标识（UUID 格式）
- Redis `ai:glue:action_lock:{action_id}` 锁（60 秒）
- Preview → Execute 使用同一 `action_id`

### 7.3 会话过期管理

| Session 类型 | TTL | 配置项 |
|-------------|-----|--------|
| ReAct Session | 可配置 | `AGENT_SESSION_TIMEOUT` |
| Workflow Session | 30 分钟 | Redis TTL |
| Pending 过期 | 3 分钟 | 稳态设计 |

---

## 八、权限控制

### 8.1 Handler 权限校验

**实现位置**：`ai_tool_service.py` → `_execute_single_tool`

**流程**：
1. 获取 Handler 配置中的 `permission_code`
2. 查询用户权限列表（`permission_service.get_user_permissions_from_db`）
3. 检查用户是否有对应权限码
4. 无权限 → 返回错误 "您没有执行此操作的权限"

**权限码示例**：
- `lead:create` - 创建线索
- `lead:follow_up:create` - 创建线索跟进
- `customer:follow_up:create` - 创建客户跟进
- `opportunity:create` - 创建商机
- `opportunity:edit:own` - 编辑自己的商机
- `contract:create` - 创建合同
- `payment:create` - 登记回款
- `invoice:create` - 申请开票

**权限码定义**：`CRM-Docs/system/GLOSSARY.md`

### 8.2 租户隔离

**实现位置**：`ActionEntry` → `_check_customer_permission`, `_check_opportunity_permission`

**规则**：
- 所有 CRUD 操作必须传入 `team_id`
- 只能操作本团队的实体
- 跨租户访问 → 返回 None（权限校验失败）

---

## 九、飞书通知集成

**暂未实现**（Phase B 计划）

**计划功能**：
- IM 渠道验签（飞书事件订阅）
- 消息去重（`message_id`）
- 异步回复（飞书开放平台 API）

**参考文档**：`CRM-Docs/requirements/AI-GLUE-REQUIREMENTS.md` → 飞书集成章节

---

## 十、关键文件路径

### 10.1 后端核心文件

| 文件 | 职责 |
|------|------|
| `app/services/ai_tool_service.py` | AI 工具服务核心（2600+ 行） |
| `app/services/ai/action_entry.py` | 入口函数层（R-1~R-5 合规） |
| `app/services/ai/action_executor.py` | CRUD 调用层 |
| `app/constants/tools.py` | Function Calling 工具定义 |
| `app/constants/handler_configs.py` | Handler 配置映射 |
| `app/constants/ai_rules.py` | AI 规则配置（风险分级） |
| `app/services/skills/handlers/` | Handler 实现目录 |

### 10.2 Handler 实现文件

| Handler | 文件 |
|---------|------|
| BaseHandler | `base_handler.py` |
| CreateHandler | `create_handler.py` |
| QueryListHandler | `query_list_handler.py` |
| QueryDetailHandler | `query_detail_handler.py` |
| StatusChangeHandler | `status_change_handler.py` |
| FollowUpHandler | `follow_up_handler.py` |
| StageAdvanceHandler | `stage_advance_handler.py` |
| AskUserHandler | `ask_user_handler.py` |
| GetContextHandler | `get_context_handler.py` |
| HandlerFactory | `handler_factory.py` |

### 10.3 API 文件

| 文件 | 说明 |
|------|------|
| `app/api/web_assistant.py` | Web AI 助手 SSE 接口 |
| `app/api/customer_ai.py` | 客户 AI 接口 |
| `app/api/lead_ai.py` | 线索 AI 接口 |
| `app/api/procurement_ai.py` | 采购流程 AI 接口 |

### 10.4 前端组件

| 组件 | 文件 |
|------|------|
| MagicWandDialog | `CRM-Client/src/components/MagicWandDialog.vue` |
| AgentProgress | `CRM-Client/src/components/AgentProgress.vue` |
| WorkflowProgress | `CRM-Client/src/components/WorkflowProgress.vue` |
| ConfirmationCard | `CRM-Client/src/components/ConfirmationCard.vue` |
| EntitySelectDialog | `CRM-Client/src/components/EntitySelectDialog.vue` |

---

## 十一、常见问题

### 11.1 AI 调用失败

**原因**：
- AI 配置未设置（`ai_config_crud.get_config` 返回 None）
- API Key 无效或过期
- LLM API 连接失败

**排查**：
1. 检查 `crm_ai_configs` 表是否有配置
2. 检查 `api_key_encrypted` 字段是否有效
3. 检查 `api_host` 是否可访问

### 11.2 权限校验失败

**原因**：
- 用户无对应权限码
- 实体不属于当前团队（租户隔离）

**排查**：
1. 检查 `crm_permissions` 表是否有对应权限码
2. 检查 `crm_user_roles` 表是否分配了包含该权限的角色
3. 检查实体的 `team_id` 是否与用户 `team_id` 一致

### 11.3 实体上下文注入失败

**原因**：
- 前端未传递 `entity_context`
- 正则匹配失败（格式不符合）

**排查**：
1. 检查前端请求是否包含 `entity_context` 字段
2. 检查 `_extract_entity_context` 正则匹配逻辑

### 11.4 ReAct 循环超时

**原因**：
- 达到最大轮数（`REACT_MAX_ROUNDS`）
- 总超时（`REACT_TOTAL_TIMEOUT`）

**排查**：
1. 检查配置项（`app/core/config.py`）
2. 检查是否陷入无限循环（AI 重复调用同一工具）

### 11.5 Session 过期

**原因**：
- ReAct Session 超过 `AGENT_SESSION_TIMEOUT`
- Workflow Session Redis TTL 过期（30 分钟）

**排查**：
1. 检查 Session ID 是否有效
2. 检查 Redis 是否正常运行

---

## 十二、相关文档

| 文档 | 路径 | 说明 |
|------|------|------|
| AI GLUE 需求文档 | `CRM-Docs/requirements/AI-GLUE-REQUIREMENTS.md` | 详细需求和规则 |
| AI GLUE 实现文档 | `CRM-Docs/system/AI-GLUE-IMPLEMENTED-FEATURES.md` | 实现状态和架构合规 |
| AI Agent 功能总结 | `CRM-Docs/plans/AI-AGENT-FEATURE-SUMMARY.md` | ReAct 循环 + Workflow 实施总结 |
| 权限码定义 | `CRM-Docs/system/GLOSSARY.md` | 权限码 + 状态枚举 |
| 架构文档 | `CRM-Docs/system/ARCHITECTURE.md` | 整体架构 |
| 系统说明 | `CRM-Docs/system/SYSTEM-DESCRIPTION.md` | 业务流程说明 |
| Handler 模板 | `CRM-Server/app/services/CLAUDE.md` | Handler 命名规范 |

---

> **文档版本**：2.0
> **最后更新**：2026-06-12
> **维护团队**：CRMWolf 开发团队