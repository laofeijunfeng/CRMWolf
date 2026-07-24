# Memory 规范

- **用途：**定义 Agent 会话记忆和任务恢复规则。
- **适用范围：**Agent 会话、消息、待确认任务、上下文补充。
- **权威性：**本文件拥有 Agent Memory 规则。
- **相关规范：**[HITL 与 Guardrails](hitl-guardrails.md) · [观测与评估](observability.md)

## 记忆来源

Agent 只能从 Agent 自有会话、消息、任务和系统 API 返回的上下文构建记忆。

不得从业务数据库绕过 API 拼接客户上下文。

## 记忆内容

- 最近用户和 Agent 消息。
- 当前待确认任务。
- 已选客户或业务对象，其中当前客户必须保存为 `session_context.current_customer`。
- 当前正在补充或等待确认的业务任务，必须保存为 `session_context.current_pending_task`。
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

创建等待任务时，必须同步写入：

- `id`
- `action`
- `intent`
- `target_id`
- `summary`

下一轮处理时，应优先读取 `current_pending_task` 指向的等待任务。

如果该任务不存在或已完成，再回退到最新等待任务。

任务进入新的等待动作时，必须更新 `current_pending_task`。

任务执行成功或被取消后，必须清理 `current_pending_task`。

## Pending 中断

存在 `current_pending_task` 时，下一轮用户输入不得无条件进入该任务。

处理顺序必须是：

- 先用 AI structured output 判断任务连续性。
- 明确是字段补充、选择或确认时，继续当前 pending。
- 明确出现新客户或新业务流程且置信度高时，暂停当前 pending 并开启新流程。
- 语义模糊时，询问用户是继续旧任务还是切换新流程。

被暂停的任务应保留在会话上下文中，避免用户后续需要恢复。

## 恢复要求

刷新页面后，会话历史和待确认任务必须可恢复。

用户确认写入时，必须基于待确认任务状态执行，不得重新猜测 payload。

## LangGraph Checkpoint

当前可保留业务自有 memory。

当多步 tool chain 增长到跨多轮恢复时，应评估 LangGraph checkpointer，用于恢复图状态而不是替代业务消息存储。
