# LangChain 采用原则

- **用途：**定义 LangChain 在 CRM AI Agent 中的采用方式。
- **适用范围：**LangChain、LangGraph、Prompt、Tool、Middleware、Memory 实现。
- **权威性：**本文件拥有 LangChain 采用边界规则。
- **相关规范：**[架构边界](architecture-boundary.md) · [结构化输出](../runtime/structured-output.md) · [交互编排策略](../runtime/interaction-policy.md)

## 采用目标

LangChain 必须解决实际工程问题，包括结构化语义理解、tool schema、middleware、HITL、观测和模型供应商适配。

只引入依赖但不进入关键链路，不视为完成采用。

## 必须使用的能力

- Structured output：用于意图、实体、时间、缺失字段和业务建议输出。
- Tool schema：每个 tool 必须有明确 Pydantic 入参模型。
- Middleware 或等价 runtime hooks：用于调用前后校验、审计、错误分类和观测。
- HITL：用于写入 tool 的 approve/edit/reject。
- Interaction planner：用于把多个候选动作裁决为单轮唯一用户交互。

## 谨慎使用的能力

自由 tool-calling agent 只能作为受控子图使用，不能直接替代确定性 CRM 流程。

初期可先开放读 tool，写 tool 必须受用户确认、上下文约束、权限 API 和幂等机制保护。

## 禁止事项

- 禁止使用正则、关键词或硬编码规则做语义理解。
- 禁止让 LLM 自行换算相对日期作为最终业务日期。
- 禁止让 LLM 直接生成数据库写入。
- 禁止在 LangChain fallback 后静默掩盖结构化输出失败。
