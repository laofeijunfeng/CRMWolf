# CRMWolf Agent 设计规范

这是 CRM AI Agent 的目标状态规范库根入口。Agent 面向“围绕客户跟进记录的智能客户关系管理系统”，当前阶段聚焦销售跟进记录、商机创建/推进和客户基础资料补充，并通过现有系统 API 执行业务动作。

## 按任务查阅

- [基础原则](foundations/README.md)：定位、架构边界、LangChain 采用原则。
- [运行时规范](runtime/README.md)：Prompt、Memory、Tool、HITL、结构化输出和观测。
- [治理规范](governance/README.md)：文档拆分、权限边界、质量检查。
- [实施路线](roadmap/README.md)：已完成能力、增强优先级和后续业务闭环。

## 规则优先级

安全与权限边界 > 业务需求文档 > Agent 设计规范 > 具体实现细节。任何实现不得绕过既有 CRM API、权限体系和审批流程。

## 核心边界

- 禁止直接操作客户、商机、合同、回款、发票等业务数据库表。
- 禁止用正则、关键词或硬编码规则做语义理解。
- 写入类 tool 必须经过用户确认。
- 创建合同第一版不支持，因为现有创建合同流程需要合同附件。
- 合同、回款、发票和 License 写入闭环不是当前阶段主目标。
- Agent 自有会话、消息、任务、tool 调用、幂等记录可以使用 Agent 自有表。

## 当前应用边界

Agent 按以下边界组织，避免 Web、飞书和后续 IM 渠道各自复制业务流程：

- Channel Adapter：只负责渠道协议适配，例如 Web SSE、飞书消息、飞书 reaction、后续企业微信/钉钉事件。
- IM Agent Gateway：只负责 IM 通道归一化和会话路由，例如把飞书 reaction 映射为通道无关的确认/拒绝输入。Gateway 禁止调用 AI 做自然语言语义分析，禁止判断 CRM 业务动作是否应该执行。
- AgentApplicationService：统一处理一轮 Agent 交互，包括会话、消息、挂起任务、确认/拒绝、补字段、调用 LangGraph、生成统一事件。
- LangGraph Orchestrator：负责确定性业务流程编排，例如语义解析、查重、客户搜索、跟进质量评估、业务上下文加载、建议生成。
- AI Capability：负责结构化语义解析、挂起任务打断判断、跟进质量评估、业务建议等模型能力。
- Tool Runtime：统一执行 CRM tool，写入类 tool 必须经过 HITL、guardrails、审计和幂等保护。
- CRM Domain/Internal Policy：承载 Agent 专用内部策略，例如创建线索/客户前的团队级去重、隐藏重复对象披露策略、排除已删除/已转化对象。

HTTP API 不应承载 Agent 业务状态机。`/v1/agent/chat/stream` 只负责鉴权、接收请求、调用 `AgentApplicationService`，并把统一事件编码为 SSE。IM 入口也必须调用同一个 `AgentApplicationService`，不能反向调用 HTTP/SSE 接口后再解析响应。

IM 文本和 IM reaction 必须进入同一个 Agent 回合模型：

- 文本输入保持文本语义，由 AgentApplicationService 和 Agent Semantic Layer 结合 pending task 判断。
- reaction 是结构化输入，允许在 IM Gateway 做平台码映射，例如飞书 `Get`/`Yes` -> 确认，`No`/`CrossMark` -> 拒绝。
- 未知 reaction 直接忽略，不交给 AI 猜测含义，避免情绪表情误触发 CRM 写操作。
- 确认/拒绝类自然语言只能在 Agent 层判断；Web、飞书、后续企业微信/钉钉不得各自维护一套确认语义。

当前实现已完成第三阶段拆分：`AgentApplicationService` 是 Web 和 IM 的统一入口，HTTP API 只负责鉴权、请求接收和 SSE 编码；Agent 运行时职责已拆到稳定服务模块：

- `session_state.py`：会话创建、归属校验、当前客户记忆、挂起任务记忆、确认/拒绝和打断判断。
- `input.py`：Web、IM 文本和 IM reaction 的通道无关 Agent 输入模型。
- `confirmation_intent.py`：可执行待确认任务的确认/拒绝/未知判断；结构化 reaction 直接判定，文本语义由 Agent AI 能力结合任务上下文判定。
- `interactions.py`：统一构造端内和 IM 可复用的 choice/form/text 交互描述。
- `task_factory.py`：从 LangGraph 事件创建等待确认的 Agent task。
- `field_common.py`：字段补全过程共用的语义补充解析和安全合并工具。
- `follow_up_fields.py`：客户/线索跟进补充、质量评估、创建后跟进任务衔接。
- `lead_fields.py`：线索字段补全和线索创建确认状态推进。
- `customer_fields.py`：客户字段补全和客户创建确认状态推进。
- `opportunity_fields.py`：商机字段补全、采购方式默认值和商机创建确认状态推进。
- `customer_related_fields.py`：联系人、发票抬头、部署信息、客户成员等客户附属资料补全。
- `payment_fields.py`：回款字段补全、合同/回款计划上下文下的下一步确认状态推进。
- `selection.py`：客户、合同、回款计划等候选项选择和后续状态推进。
- `task_actions.py`：Agent action 到 CRM tool 名称、tool payload 的映射。
- `task_execution.py`：确认后的 tool 执行、HITL guardrails、幂等和执行结果转下一步任务。

## 领域索引

- [基础原则](foundations/README.md)
- [运行时规范](runtime/README.md)
- [治理规范](governance/README.md)
- [实施路线](roadmap/README.md)
