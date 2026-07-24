# 增强优先级

- **用途：**定义下一阶段 Agent 底层增强顺序。
- **适用范围：**CRM AI Agent 后端、前端事件和测试。
- **权威性：**本文件拥有阶段性实施优先级。
- **相关规范：**[当前状态](current-state.md) · [观测与评估](../runtime/observability.md)

## P0

- 强化 structured output 失败、fallback 和来源记录。
- 前端事件展示模型、解析来源、fallback 和 tool 调用链路。
- 保证时间基准来自运行时上下文，而不是隐式服务器日期。
- 增加质量扫描，禁止语义层出现正则和关键词分类。

## P1

- 引入 middleware 或等价 runtime hooks，统一记录模型调用、tool 调用、错误分类和耗时。
- 为写入 tool 增加更完整的 HITL edit/reject 流程。
- 完善商机阶段推进的多商机选择、字段编辑和前端展示。
- 补充 LangSmith 或本地 tracing。

## P2

- 为只读 tool 引入受控 LangChain tool-calling 子 Agent。
- 在写入 tool 进入子 Agent 前接入 LangChain HITL middleware。
- 评估 LangGraph checkpointer 对复杂多轮任务恢复的价值。

## 业务扩展顺序

底层增强完成后，业务扩展按以下顺序推进：

1. 做深销售跟进记录 Agent，包括质量评估、下一步动作和时间识别。
2. 做稳商机创建、商机字段补充、动态采购阶段分析和商机推进确认。
3. 补齐客户基础资料维护，包括联系人、发票抬头、部署信息和客户成员。
4. 增加管理者查询和总结类只读能力。
5. 合同、回款、发票和 License 写入闭环放到后续阶段重新评估。
