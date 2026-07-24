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

## 领域索引

- [基础原则](foundations/README.md)
- [运行时规范](runtime/README.md)
- [治理规范](governance/README.md)
- [实施路线](roadmap/README.md)
