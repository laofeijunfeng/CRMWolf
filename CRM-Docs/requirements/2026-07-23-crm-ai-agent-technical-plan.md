# CRM AI Agent 技术实施方案

## 1. 目标与边界

本方案基于《围绕客户跟进记录的 CRM AI Agent 需求文档》，目标是新增一版轻量、清晰、生产可用的 LangGraph Agent 服务。

核心边界：

- Agent 服务负责理解自然语言、管理会话状态、编排业务 tool、输出交互结果。
- 所有 tool 必须调用系统后端现有 API 或新增的受权限保护 API。
- Agent 绝对不允许直接操作数据库。
- Agent 绝对不允许绕过权限体系。
- Agent 绝对不允许绕过后端已有业务校验、审批规则和数据隔离。
- 前端聊天 UI 优先复用 shadcn-vue `Message`、`MessageScroller` 等组件，并在业务侧封装，不重复造轮子。

## 2. 总体架构

建议新增独立的 Agent 业务模块，但仍部署在现有 FastAPI 后端中，避免第一版引入独立服务带来的认证、权限、网络和部署复杂度。

后端结构建议：

```text
CRM-Server/app/
  api/
    agent.py
  schemas/
    agent.py
  models/
    agent.py
  crud/
    agent.py
  services/
    agent/
      graph.py
      state.py
      runtime.py
      prompts.py
      intent_classifier.py
      context_builder.py
      suggestion_engine.py
      idempotency.py
      tool_registry.py
      tools/
        customer_tools.py
        follow_up_tools.py
        opportunity_tools.py
        payment_tools.py
        invoice_tools.py
        deployment_tools.py
        license_tools.py
        member_tools.py
```

前端结构建议：

```text
CRM-Client/src/
  api/
    agent.ts
  schemas/
    agent.ts
  stores/
    agent.ts
  components/
    agent/
      AgentEntryButton.vue
      AgentChatSheet.vue
      AgentConversation.vue
      AgentMessageList.vue
      AgentComposer.vue
      AgentActionCard.vue
      AgentCandidatePicker.vue
      AgentFieldCollector.vue
      AgentExecutionResult.vue
```

shadcn-vue 基础组件建议引入到：

```text
CRM-Client/src/components/ui/message/
CRM-Client/src/components/ui/message-scroller/
```

业务封装组件不得直接散落在页面中，应集中放在 `components/agent`。

## 3. LangGraph 选型与职责

LangGraph 适合作为本 Agent 的编排层，因为当前业务具备典型的状态机特征：

- 需要多轮补充信息。
- 需要用户确认后再执行写入动作。
- 需要跨天恢复未完成任务。
- 需要根据工具调用结果决定下一步。
- 需要中断、继续、重新校验和防重复。

LangGraph 不负责：

- 不直接访问数据库业务表。
- 不直接判断用户权限。
- 不直接执行 SQL。
- 不替代后端 API 的业务校验。

LangGraph 负责：

- 管理 Agent 状态。
- 决定下一步节点。
- 调用 tool。
- 在需要用户确认或补充时中断。
- 恢复会话后继续执行。
- 记录工具调用和执行结果。

## 4. Agent 状态模型

Agent state 建议包含：

```python
class AgentState(TypedDict):
    session_id: str
    task_id: str | None
    user_id: str
    team_id: int
    user_message: str
    normalized_intent: str | None
    customer_candidates: list[dict]
    selected_customer_id: int | None
    current_follow_up_id: int | None
    business_context: dict
    proposed_actions: list[dict]
    active_action: dict | None
    missing_fields: list[dict]
    confirmed_fields: dict
    pending_confirmation: dict | None
    tool_results: list[dict]
    final_response: str | None
    status: str
```

关键状态：

- `COLLECTING`：等待用户补充信息。
- `WAITING_CUSTOMER_SELECTION`：等待用户选择客户。
- `WAITING_CONFIRMATION`：等待用户确认业务写入。
- `EXECUTING`：正在调用 tool。
- `COMPLETED`：当前任务完成。
- `FAILED`：当前任务失败。

## 5. LangGraph 节点设计

建议第一版 graph 节点：

1. `load_or_create_session`

   创建或恢复 Agent 会话。

2. `classify_intent`

   判断输入是查询、跟进记录、业务推进、客户资料维护，还是继续上次任务。

3. `resolve_customer`

   通过客户搜索 API 匹配客户。唯一匹配继续；多匹配中断并让用户选择；未找到则反馈先创建客户。

4. `create_follow_up_if_required`

   对业务事实类输入自动创建客户跟进记录。资料维护类和纯查询不创建跟进记录。

5. `build_business_context`

   通过现有 API 查询客户全量上下文，包括客户、联系人、成员、商机、合同、回款计划、回款记录、发票、部署、License。

6. `generate_suggestions`

   结合用户输入和业务上下文生成最多 3 个建议。

7. `select_or_prepare_action`

   根据用户选择或当前意图确定要执行的动作。

8. `collect_missing_fields`

   只追问必填且无法可靠推断的信息。

9. `confirm_action_if_required`

   业务推进类写入必须确认。客户资料维护类按需求规则处理，设置客户成员始终确认。

10. `execute_tool`

    调用系统 API tool。

11. `post_execute_suggestion`

    根据执行结果判断是否继续建议下一步，例如 License 创建后询问是否提交审批。

12. `finalize_response`

    输出结果并保存状态。

## 6. Tool 设计原则

每个 tool 是对系统 API 的薄封装，不包含绕过 API 的业务写入逻辑。

tool 必须具备：

- 明确名称。
- 明确输入 schema。
- 明确输出 schema。
- 权限错误透传。
- 业务错误透传。
- 调用前后审计记录。
- 幂等检查。
- 当前用户 token 或服务端用户上下文传递。

tool 禁止：

- 直接读写业务数据库。
- 拼 SQL 查询业务表。
- 使用管理员身份替用户执行。
- 静默吞掉权限错误。
- 静默重试写入动作。

第一版 tool 清单：

- `search_customers`
- `get_customer_context`
- `create_customer_follow_up`
- `create_opportunity`
- `move_opportunity_stage`
- `mark_opportunity_won`
- `mark_opportunity_lost`
- `create_payment_plan`
- `create_payment_record`
- `create_invoice_application`
- `create_invoice_title`
- `create_contact`
- `create_deployment_info`
- `set_customer_member`
- `create_license_application`
- `submit_license_application`

## 7. API 适配策略

优先复用现有 API。

如果现有 API 过于分散，可新增聚合查询 API，但聚合 API 仍必须使用当前用户权限：

```text
GET /api/v1/agent/customers/{customer_id}/context
```

该 API 只做读取聚合，不改变业务数据。内部仍调用现有权限校验逻辑，保证客户、合同、回款、发票、License 等数据可见性与系统一致。

Agent 对外 API 建议：

```text
POST /api/v1/agent/sessions
GET  /api/v1/agent/sessions
GET  /api/v1/agent/sessions/{session_id}
POST /api/v1/agent/sessions/{session_id}/messages
POST /api/v1/agent/sessions/{session_id}/events
POST /api/v1/agent/sessions/{session_id}/cancel-active-task
```

其中 `messages` 用于用户输入，可返回 SSE 流。

`events` 用于用户确认、客户选择、候选对象选择、字段补充等结构化事件。

## 8. 数据表设计

第一版需要保存 Agent 会话、消息、任务、工具调用和幂等记录。

建议新增表：

### 8.1 Agent 会话表

`crm_agent_sessions`

关键字段：

- `id`
- `team_id`
- `user_id`
- `title`
- `status`
- `last_message_at`
- `created_time`
- `last_modified_time`

### 8.2 Agent 消息表

`crm_agent_messages`

关键字段：

- `id`
- `session_id`
- `role`：user/assistant/system/tool
- `content`
- `event_type`
- `payload_json`
- `created_time`

### 8.3 Agent 任务表

`crm_agent_tasks`

关键字段：

- `id`
- `session_id`
- `team_id`
- `user_id`
- `intent`
- `status`
- `selected_customer_id`
- `follow_up_id`
- `state_json`
- `pending_confirmation_json`
- `created_time`
- `last_modified_time`

### 8.4 Agent 工具调用表

`crm_agent_tool_calls`

关键字段：

- `id`
- `session_id`
- `task_id`
- `tool_name`
- `request_payload_json`
- `response_payload_json`
- `status`
- `http_status`
- `business_object_type`
- `business_object_id`
- `error_message`
- `created_time`

### 8.5 Agent 幂等记录表

`crm_agent_idempotency_keys`

关键字段：

- `id`
- `team_id`
- `user_id`
- `session_id`
- `task_id`
- `action_key`
- `tool_name`
- `request_hash`
- `status`
- `business_object_type`
- `business_object_id`
- `created_time`
- `last_modified_time`

幂等约束：

- `team_id + user_id + action_key` 唯一。
- 写入动作执行前先检查。
- 已执行动作直接返回历史结果，不重复调用写入 API。

## 9. 写入确认规则

自动执行：

- 客户唯一明确时，创建客户跟进记录可自动执行。
- 客户资料维护类动作，如果信息完整，可以直接执行，设置客户成员除外。

必须确认：

- 创建商机
- 推进商机阶段
- 标记商机赢单/输单
- 创建回款计划
- 登记回款
- 创建发票申请
- 创建 License 申请
- 提交 License 审批
- 设置客户成员
- 已有默认部署时，将新部署设为默认
- 疑似重复联系人仍要创建

执行前确认摘要应包含：

- 客户
- 动作类型
- 关键业务对象
- 金额、日期、发票抬头、合同、回款计划、佣金归属人等关键字段
- 可能影响

## 10. 幂等与错误处理

查询类 API：

- 可自动重试。
- 建议最多重试 2 次。
- 超时后反馈用户稍后重试。

写入类 API：

- 默认不自动重试。
- 执行前创建 pending 幂等记录。
- 执行成功后保存业务对象 ID。
- 执行失败后保存失败状态和错误信息。
- 结果不确定时，提示用户刷新业务对象或重新查询确认。

跨天恢复：

- 恢复 task state。
- 重新调用系统 API 校验业务对象状态和权限。
- 已执行 tool 不重复执行。
- pending 写入必须先查幂等记录和业务对象候选。

## 11. 前端实施方案

第一版采用统一 Agent 入口，建议放在主布局右上角或右下角固定入口，打开后使用 Sheet/Drawer 形式展示对话。

组件原则：

- 优先使用 shadcn-vue 官方 `Message` 和 `MessageScroller`。
- `Message` 用于标准消息行、头像、用户/助手对齐。
- `MessageScroller` 用于消息列表滚动、流式回复滚动、历史消息加载。
- 在 `components/agent` 封装业务组件，不在页面里直接拼聊天 DOM。
- 已有 `src/utils/sseParser.ts` 应继续复用，避免各 API 重复写 SSE 解析。
- 操作建议、候选客户、确认摘要、字段补充应做成结构化 action card，不只靠纯文本。

shadcn-vue 组件评估：

- `Message` 符合普通用户/助手消息展示场景。
- `Message` 不直接解决 CRM 业务动作卡片，需要业务层封装 `AgentActionCard`。
- `MessageScroller` 符合流式输出和消息容器滚动场景。
- `MessageScroller` 是无状态容器，不负责消息状态、分页、会话恢复，需要 Pinia store 和 API 层承接。
- 两者适合作为底层 UI 原语引入，不建议自造基础聊天布局。

前端状态：

- 使用 Pinia 管理当前会话、消息列表、active task、streaming 状态、pending confirmation。
- 用户确认、选择客户、补字段都作为结构化事件提交给后端。
- 前端不自行决定业务是否可执行，只展示后端 Agent 返回的候选项和确认项。

## 12. SSE 事件协议

建议 Agent SSE 事件：

```json
{"event":"message_delta","content":"正在查询客户..."}
{"event":"customer_candidates","candidates":[...]}
{"event":"follow_up_created","follow_up_id":123}
{"event":"business_context_loaded","summary":{...}}
{"event":"suggestions","suggestions":[...]}
{"event":"field_request","fields":[...]}
{"event":"confirmation_required","confirmation":{...}}
{"event":"tool_started","tool":"create_payment_record"}
{"event":"tool_result","tool":"create_payment_record","success":true,"data":{...}}
{"event":"final","message":"已完成回款登记。"}
{"event":"error","message":"没有权限创建回款记录。"}
```

所有事件必须同时保存到 Agent 消息或工具调用日志中，保证可追溯。

## 13. 安全与权限

权限执行链路：

1. 前端携带当前用户 token 调用 Agent API。
2. Agent API 通过现有认证依赖获取 `current_user` 和 `team_id`。
3. Agent tool 调用后端业务 API 时使用当前用户上下文。
4. 业务 API 继续执行现有权限校验。
5. Agent 只解释和反馈 API 结果，不越权修正。

禁止事项：

- 不允许用系统管理员 token 代替当前用户执行业务动作。
- 不允许后台直接改业务表。
- 不允许绕过 `require_permission`、`check_customer_*_permission` 等权限函数。
- 不允许在 Agent tool 内复制一套业务权限判断后直接写库。

## 14. 分阶段开发计划

### 阶段 1：Agent 基础设施

- 新增 Agent 会话、消息、任务、工具调用、幂等表。
- 新增 Agent API。
- 新增 LangGraph runtime。
- 新增 SSE 事件协议。
- 前端新增 Agent 入口、聊天容器、消息列表和输入框。
- 引入并封装 shadcn-vue `Message`、`MessageScroller`。

### 阶段 2：跟进记录闭环

- 客户识别。
- 客户候选选择。
- 自动创建跟进记录。
- 跟进质量异步评估接入。
- 客户上下文摘要查询。
- 最多 3 个主动建议。

### 阶段 3：高价值 tool MVP

建议先做：

- 创建联系人。
- 登记回款。

原因：

- 创建联系人验证资料维护类路径。
- 登记回款验证业务推进类路径、确认摘要、佣金归属人、合同/回款计划上下文和防重复。

### 阶段 4：扩展业务动作

- 创建商机。
- 推进商机阶段。
- 标记赢单/输单。
- 创建回款计划。
- 创建发票抬头。
- 创建发票申请。
- 创建部署信息。
- 创建 License 申请。
- 提交 License 审批。
- 设置客户成员。

## 15. 验收标准

技术验收：

- Agent 所有写入动作均通过系统 API 执行。
- Agent 无直接业务表读写。
- Agent tool 调用可审计。
- 写入动作具备幂等记录。
- 跨天恢复会重新校验业务状态和权限。
- SSE 流式消息稳定。
- 前端聊天 UI 使用 shadcn-vue message/message-scroller 作为底层组件。
- 前端业务卡片由 Agent 封装组件承接，不在页面中重复拼装。

业务验收：

- 客户唯一时可自动创建跟进记录。
- 客户不唯一时必须选择客户。
- 业务推进类动作必须先有跟进记录。
- 回款登记能按客户协作成员优先、owner 兜底的规则设置佣金归属人。
- 设置客户成员始终确认。
- License 创建后可继续确认提交审批。

## 16. 主要风险与应对

1. 现有 API 不完全支持 Agent 所需聚合查询

   应对：新增只读聚合 API，但必须复用现有权限校验。

2. 写入 API 缺少后端幂等键

   应对：第一版先做 Agent 侧幂等和业务重复校验；后续逐步给关键写入 API 加幂等键。

3. 用户自然语言歧义较多

   应对：客户不唯一、金额/合同/回款计划/发票抬头等关键字段不确定时必须追问或确认。

4. Agent 建议过多打扰销售

   应对：每轮最多 3 个建议，并记录本轮拒绝项不重复提示。

5. 前端聊天 UI 复杂度失控

   应对：底层复用 shadcn-vue message/message-scroller，业务层只封装 Agent action cards。

## 17. 开发前置检查清单

- 确认 LangGraph 版本和 Python 依赖安装方式。
- 确认 shadcn-vue `Message`、`MessageScroller` 组件引入方式。
- 确认 Agent 会话表迁移命名。
- 确认 Agent API 路由前缀。
- 确认内部 tool 调用 API 的认证上下文实现。
- 确认第一阶段 MVP tool 范围：创建联系人、登记回款。
- 确认是否需要新增客户上下文聚合 API。

## 18. 参考

- shadcn-vue Message：https://www.shadcn-vue.com/docs/components/message
- shadcn-vue Message Scroller：https://www.shadcn-vue.com/docs/components/message-scroller
- 需求文档：`CRM-Docs/requirements/2026-07-23-crm-ai-agent-follow-up-prd.md`
