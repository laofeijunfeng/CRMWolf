# Memory 规范

- **用途：**定义 Agent 会话记忆和任务恢复规则。
- **适用范围：**Agent 会话、消息、待确认任务、上下文补充。
- **权威性：**本文件拥有 Agent Memory 规则。
- **相关规范：**[HITL 与 Guardrails](hitl-guardrails.md) · [观测与评估](observability.md)

## 记忆来源

Agent 只能从 LangGraph checkpoint、Agent 自有会话、消息、任务投影和系统 API 返回的上下文构建记忆。

不得从业务数据库绕过 API 拼接客户上下文。

## 记忆内容

- 最近用户和 Agent 消息。
- 当前 LangGraph interrupt payload。
- 当前待确认任务投影。
- 已选客户或业务对象，其中当前客户必须保存为 `session_context.current_customer`。
- 当前正在补充或等待确认的业务任务，必须保存到 LangGraph checkpoint；历史 session pending 字段必须在 runtime projection 中剔除。
- 用户已补充但尚未执行的字段。
- 上一轮 tool 调用摘要。

## 当前客户

当前客户是跨轮业务动作的核心上下文。

当 Agent 通过客户搜索得到唯一客户、用户选择客户，或成功加载客户上下文时，必须写入：

- `id`
- `account_name`
- `owner_info`
- `collaborator_infos`

用户后续使用“那、这个客户、帮我继续”等承接表达且没有明确新客户时，LangGraph 必须优先使用 `current_customer`。

不得让模型重新猜测或搜索无关客户。

如果用户明确说出新客户名称，以本轮明确客户为准，并更新 `current_customer`。

## 当前待处理任务

字段补充、客户选择、合同选择、回款计划选择和写入确认都属于可恢复任务。

创建等待用户响应的任务时，必须先形成 LangGraph interrupt payload，再同步写入展示和审计投影：

- `id`
- `action`
- `intent`
- `target_id`
- `summary`

下一轮处理时，必须通过 `thread_id` 读取 LangGraph checkpoint 中的当前 interrupt。

如果 checkpoint 不存在或 interrupt 已完成，不得从 session context 或 `crm_agent_tasks.WAITING_USER` 反向恢复等待态；应按无当前 interrupt 的新一轮输入进入 root graph。

任务进入新的等待动作时，必须更新 checkpoint 中的 interrupt，并写入/更新 `crm_agent_tasks` 供展示和审计使用；不得向 session context 同步 pending task。

任务执行成功、被取消或被挂起后，必须通过 LangGraph resume 路由和 task 状态变更表达结果；不得依赖 session context 表达运行时暂停。

## Pending 中断

存在 LangGraph interrupt 时，下一轮用户输入不得无条件进入该任务。

处理顺序必须是：

- 先用 AI structured output 判断任务连续性。
- 明确是字段补充、选择或确认时，继续当前 pending。
- 明确出现新客户或新业务流程且置信度高时，暂停当前 pending 并开启新流程。
- 语义模糊时，询问用户是继续当前任务还是切换新流程。

被暂停的任务应保留在 LangGraph checkpoint 和任务审计投影中，避免用户后续需要恢复。

## 恢复要求

刷新页面后，会话历史和待确认任务必须通过 LangGraph checkpoint 可恢复。

用户确认写入时，必须基于待确认任务状态执行，不得重新猜测 payload。

## LangGraph Checkpoint

LangGraph checkpoint 是跨轮运行时状态的权威来源，必须覆盖所有会等待用户、可恢复、可重试、可审计的 Agent 状态。

业务自有 memory 可以继续存在，但只承担展示、审计、检索和报表职责。

必须 checkpoint 的内容包括：

- 当前客户和业务对象引用。
- 当前 interrupt payload。
- 候选客户、商机、合同、回款计划等对象集合。
- 草稿 payload、缺失字段和已补字段。
- 已裁决的 relation、action、guardrail 结果和置信度。
- 待执行 tool request、允许 tool、幂等 key 和 tool 结果摘要。
- 面向前端和 IM 的事件队列或事件摘要。

checkpoint 中不得保存不可序列化运行时对象。数据库 session、HTTP client、模型 client 和权限校验实现必须通过节点依赖注入或 service context 提供。
