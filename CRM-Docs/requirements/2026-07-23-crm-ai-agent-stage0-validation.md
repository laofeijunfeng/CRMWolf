# CRM AI Agent 阶段 0 技术验证结论

## 1. 验证目标

本次验证用于判断 CRM AI Agent 是否具备进入 MVP 开发的基础条件，重点验证：

1. LangGraph 是否能在当前后端环境运行。
2. 后端依赖声明是否完整。
3. 前端 shadcn-vue `Message`、`MessageScroller` 是否适合当前聊天场景。
4. 现有 API 是否能支撑 Agent tool 严格继承权限体系。
5. 第一阶段开发是否存在阻塞项。

## 2. 后端 LangGraph 验证

### 2.1 本地运行结果

当前 `CRM-Server/venv` 中已安装并可运行：

- Python：`3.11.2`
- `langchain_core`：`1.4.7`
- `langchain`：`1.3.9`
- `langgraph`：`1.2.5`

已完成最小 `StateGraph` 编译和执行验证，结果正常。

结论：

- LangGraph 在当前本地后端环境中可用。
- 可以作为新 CRM AI Agent 的多轮状态编排框架。

### 2.2 依赖声明缺口

当前项目存在一个需要修复的问题：

- `CRM-Server/pyproject.toml` 中没有声明 `langgraph`，并且注释仍写着此前移除过 LangGraph。
- `CRM-Server/requirements.txt` 中也没有声明 `langchain`、`langchain-core`、`langchain-anthropic`、`langgraph`。
- 本地 `venv` 能运行不代表部署环境会自动安装。

开发前必须补齐：

```text
langgraph>=1.2.5
```

同时建议统一 `pyproject.toml` 与 `requirements.txt` 的 AI 依赖策略，避免本地和部署环境不一致。

## 3. 前端 shadcn-vue 组件验证

### 3.1 当前项目状态

当前前端已经具备 shadcn-vue 项目结构：

- `CRM-Client/components.json` 存在。
- UI 组件路径为 `CRM-Client/src/components/ui`。
- aliases 已配置：
  - `@/components`
  - `@/components/ui`
  - `@/lib/utils`

当前依赖中具备 shadcn-vue 常用基础依赖：

- `reka-ui`
- `radix-vue`
- `@vueuse/core`
- `tailwind-merge`
- `class-variance-authority`

但当前项目没有：

- `CRM-Client/src/components/ui/message`
- `CRM-Client/src/components/ui/message-scroller`
- 本地 `shadcn-vue` CLI 包

### 3.2 CLI 验证结果

尝试执行：

```bash
npx shadcn-vue@latest add message --help
```

结果：

- 沙箱内执行时因无法访问 npm registry 失败。
- 联网执行后，`shadcn-vue@latest` 在当前 Node `v20.20.2` 下启动失败，错误来自 `undici` 的 `webidl.util.markAsUncloneable`。

结论：

- 不建议把 MVP 开发依赖在 `shadcn-vue@latest` CLI 自动安装上。
- 当前更稳妥的方式是按官方组件源码/registry 内容手动引入 `Message`、`MessageScroller` 到项目 UI 原语目录。
- 如后续希望使用 CLI，需要先验证或升级 Node 版本，再重新测试。

### 3.3 组件适配结论

`Message` 适合作为 Agent 聊天消息的 UI 原语，用于承载：

- 用户消息。
- AI 助手消息。
- 工具执行状态。
- 客户候选选择。
- 确认摘要。
- 字段补充请求。
- 执行结果。

`MessageScroller` 适合作为聊天主体滚动容器，用于处理：

- 消息列表滚动。
- 新消息贴底。
- 长会话查看历史。

建议实现方式：

- UI 原语：
  - `CRM-Client/src/components/ui/message/`
  - `CRM-Client/src/components/ui/message-scroller/`
- CRM 业务封装：
  - `CRM-Client/src/components/agent/AgentChatPanel.vue`
  - `CRM-Client/src/components/agent/AgentMessageList.vue`
  - `CRM-Client/src/components/agent/AgentComposer.vue`
  - `CRM-Client/src/components/agent/AgentToolCard.vue`
  - `CRM-Client/src/components/agent/AgentConfirmationCard.vue`

## 4. SSE 验证结论

当前后端已有多个 SSE API 示例：

- `CRM-Server/app/api/customer_ai.py`
- `CRM-Server/app/api/lead_ai.py`
- `CRM-Server/app/api/approval_ai.py`
- `CRM-Server/app/utils/sse_encoder.py`

当前前端已有通用 SSE 解析器：

- `CRM-Client/src/utils/sseParser.ts`

结论：

- Agent API 可以沿用 `StreamingResponse` + `data: {JSON}\n\n` 的现有格式。
- 前端应复用并扩展 `sseParser.ts`，避免每个 AI API 重复写一套解析循环。
- Agent SSE 事件可以按 MVP 文档定义实现，不存在明显技术阻塞。

## 5. API 与权限边界验证

现有后端 API 已在关键业务路由中使用当前用户和团队上下文：

- 客户：`get_current_user_team`、`get_current_active_user`、客户查看/编辑/成员权限校验。
- 跟进记录：创建前调用客户跟进权限校验。
- 回款：创建回款计划、登记回款使用 `require_permission`，查询使用当前用户和团队上下文。
- 部署信息：创建、更新、删除前校验客户编辑权限。
- 客户成员：使用客户成员管理权限校验。

结论：

- Agent tool 必须作为 HTTP/API tool 调用现有业务 API。
- Agent tool 不允许直接调用业务 CRUD，不允许直接读写业务表。
- Agent 自己可以读写 Agent 会话、消息、任务、工具调用、幂等表，用于审计和续接。

需要注意：

- 如果在后端新增 `get_customer_context` 聚合能力，也必须定义为 API 聚合层。
- 聚合层不能绕开权限直接查业务表；应调用现有 API 或复用等价的权限校验边界。
- 写入类 tool 必须传递当前用户 token 或等价认证上下文，确保权限由现有业务 API 判定。

## 6. 阶段 0 结论

CRM AI Agent MVP 具备继续实施的基础条件。

不存在阻塞 MVP 的生产级障碍，但进入开发前必须处理以下事项：

1. 补齐后端 `langgraph` 依赖声明。
2. 明确 `pyproject.toml` 与 `requirements.txt` 的依赖同步策略。
3. 不依赖 `shadcn-vue@latest` CLI 自动安装组件，改为手动引入并业务封装。
4. Agent tool 层必须走现有 API，不能直接调用业务 CRUD。
5. 新增 Agent 自有数据表只用于会话、消息、任务、审计、幂等，不承载业务数据。

## 7. 建议进入阶段 1

建议下一步进入阶段 1：

1. 补齐依赖声明。
2. 新增 Agent 数据模型与 Alembic 迁移。
3. 新增 Agent schema 与 CRUD。
4. 建立 Agent API 路由空壳和 SSE 基础响应。

第一批业务 tool 仍建议限定为：

- `search_customers`
- `get_customer_context`
- `create_customer_follow_up`
- `create_opportunity`
- `create_contact`
- `create_invoice_title`
- `create_deployment_info`
- `set_customer_member`
