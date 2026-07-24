# 观测与评估

- **用途：**定义 Agent 生产调试、审计和效果评估规则。
- **适用范围：**模型调用、结构化输出、tool 调用、HITL 和前端事件。
- **权威性：**本文件拥有 Agent 观测规则。
- **相关规范：**[结构化输出](structured-output.md) · [Tool 规范](tools.md)

## 必须记录

- session_id、task_id、team_id、user_id hash。
- 模型供应商、模型名称、Prompt 版本。
- structured output 来源和是否 fallback。
- 语义 intent、置信度、缺失字段和澄清状态。
- tool 名称、入参摘要、执行结果和错误分类。
- HITL 决策和执行时间。

## 用户可验证

前端事件或调试信息应能回答：

- 是否走了 AI。
- 使用了哪个模型。
- 是否命中 structured output。
- 是否调用了 CRM API tool。
- 哪一步需要用户确认。

## LangSmith

生产环境建议接入 LangSmith 或等价 tracing 平台。

未接入前，必须保留本地 trace event，避免模型、Prompt、tool 和业务 API 问题混在一起无法定位。
