# CRMWolf 销售助手规范

现行入口是 Web `/assistant`，通过 `/v1/assistant` 录入客户活动，并在活动提交后独立处理跟进任务及商机建议。旧 `/agent` 不再接收新输入，见 [ADR 0003](../../docs/adr/0003-legacy-agent-entry-retirement.md)。

模型负责提取语义、证据和候选；服务端负责校验真实对象、确定唯一当前交互、授权、幂等与执行。页面只投影权威任务状态和回执，不通过文案推断业务结果。

| 查阅 | 规范 |
| --- | --- |
| 产品边界 | [产品定位](foundations/product-positioning.md) |
| 前端与交互 | [Agent UI 平台边界](runtime/agent-ui-platform.md) · [交互编排策略](runtime/interaction-policy.md) |
| 模型与质检 | [结构化输出](runtime/structured-output.md) · [跟进质量评估](runtime/follow-up-quality.md) |
| 写入与恢复 | [销售助手命令契约](runtime/assistant-command-contract.md) · [权限边界](governance/permission-boundary.md) |
| 领域规则 | [客户活动实施规格](roadmap/customer-activity-workflow-parity-spec.md) · [ADR 0001](../../docs/adr/0001-customer-activity-workflow-parity.md) |
| 文档与评审 | [治理规范](governance/README.md) |
