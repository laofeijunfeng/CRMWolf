# 运行时规范

本领域定义 Agent 在实际请求中的 Prompt、Memory、Tool、HITL、结构化输出和观测规则。

| 主题 | 使用场景 |
| --- | --- |
| [Prompt 规范](prompts.md) | 编写或修改语义解析、建议生成和 tool-calling Prompt。 |
| [结构化输出](structured-output.md) | 定义 AI 输出 schema、校验和 fallback 行为。 |
| [交互编排策略](interaction-policy.md) | 选择单轮唯一用户交互动作和动作优先级。 |
| [Tool 规范](tools.md) | 新增或修改 Agent tool。 |
| [Memory 规范](memory.md) | 会话记忆、待确认任务和上下文恢复。 |
| [HITL 与 Guardrails](hitl-guardrails.md) | 写入确认、执行保护和用户确认链路。 |
| [观测与评估](observability.md) | 判断是否走 AI、效果调试和生产审计。 |

[返回 Agent 根入口](../README.md)
