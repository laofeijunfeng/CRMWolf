# 权限边界

- **用途：**定义 Agent 权限和数据访问红线。
- **适用范围：**Tool、Runtime、Graph、API、测试。
- **权威性：**本文件拥有 Agent 权限边界规则。
- **相关规范：**[Tool 规范](../runtime/tools.md) · [架构边界](../foundations/architecture-boundary.md)

## 绝对禁止

- 直接调用业务 CRUD 创建或修改客户、商机、合同、回款、发票等对象。
- 直接访问业务 model/table 拼接权限外上下文。
- 以系统身份替代当前用户执行业务 API。
- 绕过审批流程、通知流程或 API 校验。

## 必须遵守

tool 调用必须携带当前用户授权信息。

业务 API 返回无权限、无数据或校验失败时，Agent 必须如实反馈，不得改写为成功。

## 允许范围

Agent 可以访问 Agent 自有会话、消息、任务、tool 调用和幂等记录。

这些数据只能用于恢复对话、审计和执行保护，不能替代 CRM 业务对象。
