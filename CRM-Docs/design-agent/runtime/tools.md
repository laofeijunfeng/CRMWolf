# Tool 规范

- **用途：**定义 CRM AI Agent tool 的注册、调用和权限边界。
- **适用范围：**所有 Agent read/write tool。
- **权威性：**本文件拥有 tool 规则。
- **相关规范：**[HITL 与 Guardrails](hitl-guardrails.md) · [架构边界](../foundations/architecture-boundary.md)

## 唯一实现方式

所有 tool 必须调用现有 CRM 后端 API。

绝对不允许直接操作业务数据库，绝对不允许绕过权限体系、审批流程和通知逻辑。

## 注册要求

每个 tool 必须在 allowlist registry 中注册，并声明：

- tool 名称。
- 业务说明。
- Pydantic 入参模型。
- 是否写入类 tool。
- 是否需要用户确认。
- 对应现有 CRM API。

## 执行要求

tool 执行必须携带当前用户授权上下文。

写入类 tool 必须存在确认任务、用户确认结果、允许的 tool 名称和允许的客户上下文。

创建商机属于写入类 tool，必须调用现有 `POST /v1/opportunities/`。

商机创建后由现有 API 自动提交审批，Agent 不得绕过审批流程。

创建商机的字段要求必须以 API 内部逻辑为准，不只看请求 schema。`opportunity_name` 由后端按客户、用户数和授权模式生成，Agent tool 不传该字段，也不向用户追问。

商机推进相关 tool 必须调用现有商机 API：

- `GET /v1/opportunities/` 查询客户商机。
- `GET /v1/opportunities/{id}` 获取商机详情。
- `GET /v1/opportunities/{id}/procurement-stages` 获取动态采购阶段。
- `POST /v1/opportunities/{id}/move-stage` 在用户确认后推进阶段。

阶段名称和阶段顺序必须来自 API 返回，Agent 不得硬编码采购阶段。

如果跟进记录语义同时触发阶段推进，执行链路必须先确认并创建跟进记录，再把阶段推进转成下一步确认任务。

如果跟进记录语义同时触发创建商机建议，最终回复先确认跟进记录；跟进记录成功后再询问是否继续处理商机。

系统当前没有跟进提醒 tool，不得把 `next_follow_time` 转成独立提醒动作。

当前阶段 tool 优先级：

- P0：`create_customer_follow_up`、`search_customers`、`get_customer_context`。
- P0：`create_opportunity`、商机阶段读取和 `move_opportunity_stage`。
- P1：`create_contact`、`create_invoice_title`、`create_deployment_info`、`set_customer_member`。
- P2：管理者查询类只读 tool，例如客户概览、商机进展、销售跟进摘要。
- P3：回款、发票和 License 写入类 tool，只有在业务边界重新确认后扩展。

创建合同暂不纳入 tool，因为现有合同创建要求上传合同附件。

## 输出要求

tool 结果必须标准化为成功、失败、错误信息、业务数据和可审计事件。

API 错误不得被模型改写为“已成功”。
