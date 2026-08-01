# 当前状态

- **用途：**记录 CRM AI Agent 当前能力边界。
- **适用范围：**阶段性验收、后续开发排期。
- **权威性：**本文件只记录当前认知，具体规则以 foundations/runtime 为准。
- **相关规范：**[增强优先级](enhancement-priority.md)

## 已具备

- Root graph 已成为 Agent 正常运行时入口，承担 thread/checkpoint、pending/new-flow/confirmed-task 路由、interrupt/resume 和最终输出聚合。
- LangGraph checkpoint 已进入 root、pending、pending preflight、pending interaction、new-flow、confirmed-task 和多个领域 subgraph；跨轮等待状态优先从 checkpoint 恢复。
- 选择、补字段、文本补充、写入确认和暂停草稿归属澄清已接入 `interrupt()` / `Command(resume=...)` 主链路；`crm_agent_tasks` 保留为前端展示和审计投影。
- Pending interaction 已从旧 planner 拆为显式 LangGraph 节点、handler registry 和 conditional edge，字段补充、客户选择、业务对象选择由 pending interaction subgraph 承载。
- Confirmed-task/tool 执行已进入 dedicated subgraph，继续复用 tool registry、HITL guardrails、幂等和 CRM API 边界。
- 新流程已经拆出客户识别、重复检查、业务上下文、行动规划、跟进质量、商机、客户资料维护、回款登记等领域 subgraph。
- Root checkpoint 记录 pending/new-flow 的 checkpoint-safe result projection，例如 `pending_task_result`、`new_flow_result`、`current_interrupt`、`assistant_content` 和分支事件。
- Root runtime 已暴露 LangGraph state history/time-travel 基础接口，可按 checkpoint id 回读 JSON-safe 状态投影、interrupt、resume payload 和分支事件。
- AI structured output 语义解析。
- AI structured output 业务建议生成。
- Agent 会话、消息和待确认任务存储。
- Tool allowlist 和 Pydantic 入参模型。
- 写入 tool 的自定义 HITL guardrails。
- 客户搜索、客户上下文、跟进记录、联系人、发票抬头、部署信息、回款计划、回款登记 tool。

## 未充分具备

- LangGraph 已是正常路径的运行时入口；session/task projection 不得承担等待态恢复，`crm_agent_tasks` 仅保留展示、审计和新等待事件投影职责。
- Checkpoint 已覆盖主要等待链路，root state history/time-travel 基础接口已具备；跨服务重启后的端到端回放和前端 trace 展示还不完整。
- HITL native migration 已覆盖主要 pending interaction；仍需继续审计是否存在 application/session 层可绕过 root graph 的恢复路径。
- Domain subgraph decomposition 已形成骨架和多个业务子图；商机阶段推进、合同/发票/License 等更深业务闭环尚未完全图原生化。
- LangChain middleware 未进入主业务链路。
- LangChain HITL middleware 仅有适配函数，尚未用于 tool-calling 子 Agent。
- structured output fallback 缺少更强审计和失败原因暴露。
- LangSmith 或等价 tracing 尚未接入。
- 前端调试事件还不能完整回答模型来源、fallback、tool 调用链路和当前交互阻塞点。
- 部分候选动作、对象选择、字段补全和业务建议仍需要更明确的执行层裁决，避免依赖 prompt 文案约束。

## 当前判断

现阶段不应围绕单点业务继续堆叠图外流程分支。新增业务能力必须优先进入 root graph + domain subgraph + interrupt/resume + checkpoint 的运行时结构。

下一步优先级是补齐 state history/trace、扩大领域子图覆盖面，并增加跨服务重启的端到端恢复测试；商机阶段推进应在这些原则下作为 opportunity subgraph 的业务迭代实现。

Agent 可靠性优化的主线不是扩大模型权限，而是减少模型需要猜测的决策点。自然语言理解保留给模型；确定性业务选择、权限、状态、日期、枚举、对象 ID、tool 执行和成功失败判定应继续下沉到代码和现有 CRM API。
