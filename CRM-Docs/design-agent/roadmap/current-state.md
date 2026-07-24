# 当前状态

- **用途：**记录 CRM AI Agent 当前能力边界。
- **适用范围：**阶段性验收、后续开发排期。
- **权威性：**本文件只记录当前认知，具体规则以 foundations/runtime 为准。
- **相关规范：**[增强优先级](enhancement-priority.md)

## 已具备

- LangGraph 确定性流程编排。
- AI structured output 语义解析。
- AI structured output 业务建议生成。
- Agent 会话、消息和待确认任务存储。
- Tool allowlist 和 Pydantic 入参模型。
- 写入 tool 的自定义 HITL guardrails。
- 客户搜索、客户上下文、跟进记录、联系人、发票抬头、部署信息、回款计划、回款登记 tool。

## 未充分具备

- LangChain middleware 未进入主业务链路。
- LangChain HITL middleware 仅有适配函数，尚未用于 tool-calling 子 Agent。
- structured output fallback 缺少更强审计和失败原因暴露。
- LangSmith 或等价 tracing 尚未接入。
- LangGraph checkpointer 尚未用于复杂多轮状态恢复。

## 当前判断

现阶段不需要推倒重来。

下一步应先补 Prompt、Memory、Tool、Guardrails 和 Observability 的生产级细节，再扩展更多业务闭环。
