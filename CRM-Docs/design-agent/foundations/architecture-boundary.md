# 架构边界

- **用途：**定义 Agent 各层职责和不可跨越的边界。
- **适用范围：**后端服务、LangGraph 编排、LangChain 调用、Tool 实现。
- **权威性：**本文件拥有 Agent 架构边界规则。
- **相关规范：**[LangChain 采用原则](langchain-principles.md) · [Tool 规范](../runtime/tools.md)

## 分层职责

- LangChain：负责模型调用、结构化输出、tool-calling 子 Agent、middleware 能力。
- LangGraph：负责确定性业务流程编排、状态流转和后续可恢复执行。
- Agent Runtime：负责 tool 执行入口、guardrails、幂等和执行结果标准化。
- CRM API：负责真实业务读写、权限校验、审批和通知。
- Agent 自有存储：负责会话、消息、待确认任务、tool 调用记录和幂等键。

## 不可跨越边界

- Agent tool 不得直接访问客户、商机、合同、回款、发票等业务 CRUD/model/table。
- Agent 不得绕过 CRM API 的权限、审批和通知逻辑。
- AI 不得直接决定执行写入动作；写入动作必须经过 HITL。
- Prompt 不得要求模型编造客户、合同、回款计划或对象 ID。

## 推荐编排方式

受控 CRM 流程优先由 LangGraph 编排，LangChain 用于语义理解、业务建议和受控 tool-calling 子图。

当业务链路涉及多步写入时，每一步写入都必须有明确上下文、确认任务和可审计 tool 调用记录。
