# CRM AI Agent MVP 开发任务拆分清单

## 1. MVP 目标

第一版 MVP 不追求覆盖所有业务 tool，而是先打通生产级 Agent 的最小闭环：

1. 统一 Agent 对话入口。
2. Agent 会话、消息、任务、工具调用、幂等记录可保存。
3. 基于 LangGraph 管理多轮状态。
4. 基于 LangChain structured output 完成 AI 语义解析，不使用正则、关键词或硬编码规则做语义理解。
5. Prompt、Memory、Tool Registry、Middleware/Guardrails 模块化，并有测试约束。
6. 客户识别与客户候选选择。
7. 客户唯一明确时自动创建客户跟进记录。
8. 查询客户上下文并生成业务摘要。
9. 支持当前阶段高价值 tool：
   - 创建商机，验证跟进记录驱动商机创建和字段补充。
   - 创建联系人，验证客户资料维护类动作。
   - 创建发票抬头、创建部署信息、设置客户成员按实现节奏补齐。
10. 所有业务 tool 只调用现有 API，不直接操作数据库，不绕过权限体系。
11. 前端聊天 UI 复用 shadcn-vue `Message`、`MessageScroller`，并做业务封装。

## 2. MVP 不做范围

- 不创建客户。
- 不创建合同。
- 不上传合同附件。
- 不上传发票文件。
- 不把回款、发票和 License 写入闭环作为当前阶段主目标。
- 不接入全部业务 tool。
- 不做通用编辑已有对象。
- 不做删除、撤销。
- 不直接审批业务单据。
- 不绕过系统 API。
- 不绕过权限体系。
- 不直接读写业务数据库。
- 不使用正则表达式、关键词匹配或硬编码规则做意图识别、实体抽取、下一步动作理解和缺失字段语义判断。
- 不返回 mock 业务执行结果。

## 3. 开发阶段拆分

建议按 6 个阶段推进，每个阶段都可独立验收。

## 4. 阶段 0：开发前准备

### 4.1 确认依赖

任务：

- 确认后端 Python 版本与 LangGraph 可用版本。
- 确认需要新增依赖：
  - `langgraph`
  - LangChain `create_agent`、structured output、middleware、HITL/checkpointer 所需依赖。
- 确认依赖写入 `CRM-Server/requirements.txt` 的版本策略。

验收：

- 本地后端环境可安装依赖。
- FastAPI 启动不受影响。

### 4.2 确认 shadcn-vue 组件引入方式

任务：

- 确认 `Message`、`MessageScroller` 是否可通过 shadcn-vue CLI 添加。
- 如果 CLI 不适配当前项目，按官方组件源码引入到：
  - `CRM-Client/src/components/ui/message/`
  - `CRM-Client/src/components/ui/message-scroller/`
- 保持组件作为 UI 原语，不写 CRM 业务逻辑。

验收：

- 两个组件可被业务组件正常 import。
- 不破坏现有 shadcn-vue 组件目录结构。

### 4.3 确认 MVP tool 顺序

任务：

- 第一批 tool 固定为：
  - `search_customers`
  - `get_customer_context`
  - `create_customer_follow_up`
  - `create_opportunity`
  - `create_contact`
  - `create_invoice_title`
  - `create_deployment_info`
  - `set_customer_member`
- 回款、发票和 License 写入 tool 只预留接口，不实现业务闭环。

验收：

- 团队确认第一版以跟进记录和商机为主线，不因合同、回款、发票和 License 完整链路阻塞上线。

## 5. 阶段 1：数据库与后端基础设施

### 5.1 新增 Agent 数据模型

任务：

- 新增 `CRM-Server/app/models/agent.py`。
- 定义以下表模型：
  - `crm_agent_sessions`
  - `crm_agent_messages`
  - `crm_agent_tasks`
  - `crm_agent_tool_calls`
  - `crm_agent_idempotency_keys`
- 在 `CRM-Server/app/models/__init__.py` 注册模型。

验收：

- 模型可被 Alembic 识别。
- 字段包含 `team_id`、`user_id`、`created_time`、`last_modified_time` 等审计字段。

### 5.2 新增 Alembic 迁移

任务：

- 新增迁移文件创建 Agent 相关表。
- 为常用查询字段建立索引：
  - `team_id`
  - `user_id`
  - `session_id`
  - `task_id`
  - `status`
  - `created_time`
- 为幂等表建立唯一约束：
  - `team_id + user_id + action_key`

验收：

- `alembic upgrade head` 成功。
- 可回滚迁移。

### 5.3 新增 Agent Schema

任务：

- 新增 `CRM-Server/app/schemas/agent.py`。
- 定义：
  - 会话创建/响应 schema。
  - 消息响应 schema。
  - SSE 事件 schema。
  - 用户事件 schema。
  - 确认摘要 schema。
  - 客户候选 schema。
  - 字段补充 schema。

验收：

- API 响应结构稳定。
- 前端可基于 schema 建 zod 类型。

### 5.4 新增 Agent CRUD

任务：

- 新增 `CRM-Server/app/crud/agent.py`。
- 实现：
  - 创建会话。
  - 追加消息。
  - 创建/更新任务。
  - 记录 tool 调用。
  - 创建/查询/更新幂等记录。

注意：

- CRUD 只操作 Agent 自己的会话和审计表。
- CRUD 不读写 CRM 业务表。

验收：

- 单元测试覆盖基础 CRUD。
- 不出现业务表写入逻辑。

## 6. 阶段 2：Agent API 与 SSE

### 6.1 新增 Agent API 路由

任务：

- 新增 `CRM-Server/app/api/agent.py`。
- 在 `CRM-Server/app/main.py` 注册路由。
- API 前缀建议：
  - `/api/v1/agent`

接口：

```text
POST /api/v1/agent/sessions
GET  /api/v1/agent/sessions
GET  /api/v1/agent/sessions/{session_id}
POST /api/v1/agent/sessions/{session_id}/messages
POST /api/v1/agent/sessions/{session_id}/events
```

验收：

- 所有接口使用当前登录用户上下文。
- 所有接口受认证保护。
- 用户只能访问自己的 Agent 会话，管理员范围另行定义，MVP 不做。

### 6.2 实现 SSE 响应

任务：

- `POST /messages` 返回 `StreamingResponse`。
- 复用现有 SSE 编码习惯。
- 事件格式统一为 `data: {JSON}\n\n`。

MVP SSE 事件：

```text
thinking
message_delta
customer_candidates
follow_up_created
business_context_loaded
suggestions
field_request
confirmation_required
tool_started
tool_result
final
error
```

验收：

- 前端可连续接收事件。
- 后端异常能输出 `error` 事件，并保存日志。
- 不用纯调试文本替代结构化业务事件。
- `final` 明确区分已完成、等待用户确认、缺信息、权限不足和失败。

### 6.3 用户结构化事件

任务：

- `POST /events` 支持：
  - 选择客户。
  - 确认执行，对应 `approve`。
  - 编辑确认字段，对应 `edit`。
  - 拒绝建议。
  - 补充缺失字段。
  - 选择候选业务对象。
  - 普通补充回答，对应 `respond`。

验收：

- Agent 可从等待状态恢复继续执行。
- 用户刷新页面后仍能继续未完成任务。

## 7. 阶段 3：LangGraph Runtime

### 7.1 Agent State

任务：

- 新增 `CRM-Server/app/services/agent/state.py`。
- 定义 Agent 状态 TypedDict 或 Pydantic model。
- 支持序列化到 `crm_agent_tasks.state_json`。
- 状态包含 Agent memory 摘要、结构化语义结果、guardrail 检查结果、pending HITL 决策、幂等 key 和 tool 执行结果。

验收：

- 状态可保存、恢复、继续执行。
- 状态中不保存敏感 token。

### 7.2 Prompt 与结构化语义解析

任务：

- 新增 `CRM-Server/app/services/agent/prompts.py`。
- 新增 `CRM-Server/app/services/agent/semantic.py`。
- 定义 CRM 业务 system prompt，覆盖产品定位、输入类型、API/权限边界、低置信度追问、候选不唯一确认、禁止规则式语义解析。
- 使用 LangChain structured output 或等价 Pydantic schema 约束输出：
  - intent
  - confidence
  - customer_name
  - follow_up_content
  - next_action
  - next_follow_time
  - entities
  - missing_fields
  - proposed_actions
  - clarification_question

验收：

- 语义解析主路径调用系统配置的 AI 供应商。
- 不存在正则/关键词/硬编码意图分类器。
- Pydantic 校验失败时重新请求结构化输出或进入追问，不用正则兜底。
- 单元测试覆盖典型输入、低置信度、字段缺失、模型返回非法结构。

### 7.3 Memory 服务

任务：

- 新增 `CRM-Server/app/services/agent/memory.py`。
- 读取 Agent 自有会话、消息、任务、确认、工具调用和幂等状态。
- 为语义解析和建议生成提供最近上下文摘要。

验收：

- Memory 不读取 CRM 业务表。
- Memory 不把旧业务上下文当成当前事实。
- 恢复任务后，进入业务动作前必须重新调用系统 API 校验对象状态和权限。

### 7.4 Agent Graph

任务：

- 新增 `CRM-Server/app/services/agent/graph.py`。
- 实现 MVP 节点：
  - `load_memory`
  - `semantic_parse`
  - `apply_input_guardrails`
  - `resolve_customer`
  - `create_follow_up_if_required`
  - `build_business_context`
  - `generate_suggestions`
  - `prepare_action`
  - `collect_missing_fields`
  - `confirm_action_if_required`
  - `execute_tool`
  - `apply_output_guardrails`
  - `finalize_response`

验收：

- 查询类输入不创建跟进记录。
- 业务事实类输入在客户唯一时自动创建跟进记录。
- 客户不唯一时进入等待选择状态。
- 缺字段时进入等待补充状态。
- 需要确认时进入等待确认状态。
- 等待确认、字段补充、客户选择都可刷新后恢复。

### 7.5 Middleware 与 Guardrails

任务：

- 新增 `CRM-Server/app/services/agent/middleware.py`。
- 新增 `CRM-Server/app/services/agent/guardrails.py`。
- 实现 tool allowlist、写入确认校验、写入禁止自动重试、查询有限重试、工具调用审计、权限/API 错误标准化。
- 拦截直接数据库操作、伪造对象 ID、绕过审批/权限等输入指令。
- 拦截“已完成但实际未执行 API”的输出。

验收：

- 业务写入没有确认摘要和幂等 key 时不能执行。
- 模型臆造的业务对象 ID 不能进入 tool。
- 用户要求绕过权限/数据库直改时被拒绝。
- 权限错误如实反馈给用户。

### 7.6 客户识别

任务：

- 使用现有客户搜索/列表 API。
- 输出客户候选。
- 唯一匹配继续。
- 多匹配要求用户选择。
- 未找到提示先创建客户。

验收：

- 不唯一时不得创建跟进记录。
- 未找到客户时不得创建客户。

## 8. 阶段 4：MVP Tool 实现

### 8.1 Tool Registry

任务：

- 新增 `tool_registry.py`。
- 注册 tool 名称、描述、输入 schema、输出 schema、执行函数、是否写入、是否需要确认、允许的 HITL 决策类型、幂等策略、审计对象类型。
- 提供 LangChain `StructuredTool` 导出能力。
- tool 入参必须先通过 Pydantic schema 校验。
- 所有 tool executor 只能调用系统现有 API。

验收：

- 所有 tool 调用经过统一入口。
- 所有写入 tool 都记录 tool call。
- Graph 节点不直接调用具体业务函数。
- Agent service/API 中不出现业务 CRUD、业务 ORM model、SQL 查询或数据库连接操作。
- Tool Registry 有单元测试覆盖 allowlist、schema 校验、确认要求和 API 错误透传。

### 8.2 客户上下文 Tool

任务：

- 实现 `get_customer_context`。
- 优先复用现有 API。
- 如果现有 API 分散导致 Agent 反复调用，第一版先由 `get_customer_context` 编排调用现有 API。
- 确需新增聚合查询能力时，必须先作为标准业务 API 设计、验收权限与数据隔离，再纳入 Agent tool；Agent 不得为了聚合上下文直接查业务数据库。

聚合范围 MVP：

- 客户基本信息。
- 联系人。
- 客户成员。
- 最近跟进记录。
- 商机。
- 合同。
- 回款计划。
- 回款记录。

验收：

- 只读。
- 权限与现有客户详情一致。
- 无直接绕过权限的数据泄露。

### 8.3 创建跟进记录 Tool

任务：

- 实现 `create_customer_follow_up`。
- 调用现有跟进记录 API。
- 默认跟进方式为“其他/未指定沟通”。
- 保存返回的跟进记录 ID。

验收：

- 客户唯一时自动创建。
- 客户不唯一不创建。
- 创建后触发现有异步质量评估逻辑。

### 8.4 创建联系人 Tool

任务：

- 实现 `create_contact`。
- 调用现有客户联系人创建 API。
- 缺少必填字段时追问：
  - 姓名
  - 性别
  - 职务
  - 手机号
- 同客户疑似重复联系人时，要求用户确认是否仍创建。

验收：

- 客户资料维护类动作不强制创建跟进记录。
- 信息完整且无重复风险时可直接创建。
- 疑似重复时必须确认。

### 8.5 回款场景处理

任务：

- 识别用户输入中的回款事实并创建客户跟进记录。
- 通过现有 API 查询客户商机、合同和回款计划上下文。
- 按客户 -> 商机 -> 合同 -> 回款计划 -> 登记回款链路判断缺失环节。
- 没有商机时优先建议创建商机。
- 没有合同时说明合同环节缺失，并引导用户回到系统处理。
- 当前阶段不把登记回款作为主闭环，除非实施计划重新明确纳入。

验收：

- 业务推进类动作必须先创建跟进记录。
- 不跳过商机和合同前置条件。
- 不建议在无合同时创建回款计划。
- 不建议在无回款计划时登记回款。
- 输出说明精准、简短，并给出下一步系统操作建议。

## 9. 阶段 5：前端 Agent 入口与聊天 UI

### 9.1 引入 shadcn-vue Message 组件

任务：

- 引入 `Message` 到：
  - `CRM-Client/src/components/ui/message/`
- 引入 `MessageScroller` 到：
  - `CRM-Client/src/components/ui/message-scroller/`
- 保持组件源码接近官方，不加入业务逻辑。

验收：

- 可在 Agent 业务组件中 import。
- 基础消息布局正常。

### 9.2 Agent API Client

任务：

- 新增 `CRM-Client/src/api/agent.ts`。
- 实现：
  - 创建会话。
  - 获取会话。
  - 获取消息。
  - 发送消息并解析 SSE。
  - 发送用户事件。
- 复用 `src/utils/sseParser.ts`。

验收：

- 不重复写 SSE parser。
- token 传递与现有 request 体系一致。

### 9.3 Agent Store

任务：

- 新增 `CRM-Client/src/stores/agent.ts`。
- 管理：
  - 当前会话。
  - 消息列表。
  - streaming 状态。
  - 客户候选。
  - 待确认动作。
  - 缺失字段。
  - tool 执行结果。

验收：

- 刷新后可恢复会话。
- SSE 事件能正确更新 UI。

### 9.4 Agent 业务组件

任务：

- 新增：
  - `AgentEntryButton.vue`
  - `AgentChatSheet.vue`
  - `AgentConversation.vue`
  - `AgentMessageList.vue`
  - `AgentComposer.vue`
  - `AgentActionCard.vue`
  - `AgentCandidatePicker.vue`
  - `AgentFieldCollector.vue`
  - `AgentExecutionResult.vue`

设计要求：

- 不做营销式页面。
- 入口轻量，不干扰主 CRM 操作。
- 操作建议、候选客户、确认摘要、字段补充都用结构化卡片。
- 卡片内部使用现有 Button、Input、Textarea、Select、DatePicker、Badge 等 shadcn-vue/本地封装组件。

验收：

- 消息展示基于 `Message`。
- 滚动容器基于 `MessageScroller`。
- 业务动作 UI 在 `components/agent` 中封装。
- 移动端和桌面端不出现文字溢出或控件重叠。

### 9.5 主布局接入

任务：

- 在 `CRM-Client/src/AppLayout.vue` 接入 Agent 入口。
- 入口位置建议为右上角工具区或右下角固定按钮，最终按现有布局选择。

验收：

- 登录后可见。
- 未登录不可用。
- 不影响现有导航和业务页面。

## 10. 阶段 6：测试与验收

### 10.1 后端测试

任务：

- Agent CRUD 单元测试。
- 幂等逻辑测试。
- Prompt/semantic structured output 测试。
- Memory 读取范围测试。
- Tool Registry schema/allowlist/确认要求测试。
- Middleware/Guardrails 测试。
- 客户识别测试。
- 跟进记录自动创建测试。
- 创建联系人 tool 测试。
- 创建商机 tool 测试。
- 客户资料维护 tool 测试。
- 回款链路建议测试。
- 权限错误透传测试。
- 禁止正则/关键词语义解析扫描测试。
- 禁止业务 DB 直连/业务 CRUD 调用扫描测试。

关键用例：

- 客户唯一，自动创建跟进记录。
- 客户不唯一，不创建跟进记录。
- 客户不存在，提示先创建客户。
- 商机字段补充跨多轮不丢失。
- 无商机客户提到回款时，优先建议创建商机。
- 当前用户无权限时，Agent 反馈权限错误。
- AI 供应商未配置时，不返回 mock 业务结果。
- 模型解析低置信度时进入追问。

### 10.2 前端测试

任务：

- Agent store 测试。
- SSE 事件处理测试。
- 候选客户选择测试。
- 确认摘要交互测试。
- 缺失字段补充测试。

验收：

- `npm run type-check` 不引入新的类型错误。
- 关键组件有基础单测。

### 10.3 端到端验收场景

场景 1：创建跟进记录

输入：

```text
今天和越秀金融的王总沟通了项目进展，客户还在立项评估，下周三再确认
```

预期：

- Agent 匹配客户。
- 客户唯一时自动创建跟进记录。
- 写入下次动作和下次跟进时间。
- 返回创建结果。
- 查询客户上下文。
- 提出最多 3 个建议。

场景 2：客户不唯一

输入：

```text
今天和光大王总聊了回款
```

预期：

- 返回候选客户。
- 用户选择前不创建跟进记录。

场景 3：创建联系人

输入：

```text
帮我给越秀金融创建联系人王总，手机号 13800000000，职位采购负责人
```

预期：

- 不强制创建跟进记录。
- 如性别缺失，追问或使用产品确认的默认策略。
- 无重复风险时创建联系人。

场景 4：回款事实识别

输入：

```text
光大证券今天回款了
```

预期：

- 自动创建跟进记录。
- 查询客户商机、合同和回款计划。
- 没有商机时优先建议创建商机。
- 有商机但没有合同时说明合同环节缺失。
- 不跳过合同直接建议创建回款计划。
- 当前阶段不自动登记回款。

## 11. 建议提交节奏

建议按阶段提交，避免一个大提交难 review：

1. `docs: add crm ai agent mvp task breakdown`
2. `feat(agent): add backend agent persistence models`
3. `feat(agent): add agent api and sse runtime`
4. `feat(agent): add prompt memory semantic foundation`
5. `feat(agent): add tool registry middleware guardrails`
6. `feat(agent): add langgraph mvp flow`
7. `feat(agent): add follow-up and customer context tools`
8. `feat(agent): add opportunity and customer profile tools`
9. `feat(agent-ui): add chat shell and message components`
10. `feat(agent-ui): wire agent conversation flow`

## 12. 开工前必须确认项

以下事项确认后再进入代码开发：

1. 是否同意 MVP 先做“跟进记录 + 创建商机 + 客户资料维护”业务 tool。
2. 是否同意新增 Agent 自有会话/审计/幂等表。
3. 是否同意客户上下文第一版先由现有 API 编排完成；确需聚合查询时，先补标准业务 API。
4. 是否同意后端 Agent 模块放在现有 FastAPI 服务内。
5. 是否同意前端统一入口先接入 `AppLayout.vue`。
6. 是否同意通过 shadcn-vue 官方组件或源码方式引入 `Message`、`MessageScroller`。
7. 是否同意底层先完成 Prompt、Memory、Tool Registry、Middleware/Guardrails，再扩展更多业务 tool。

确认后即可从阶段 1 开始开发。
