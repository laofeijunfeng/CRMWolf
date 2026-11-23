# 销售助手命令契约

适用于 Web `/assistant` → `/v1/assistant`。任务、轮次、签发动作和命令账本由服务端持有；模型只提名，不授权或执行写入。同步请求、持久任务及恢复不得引入 LangGraph、LangChain 或旧 Agent 编排器。领域原子以 [ADR 0001](../../../docs/adr/0001-customer-activity-workflow-parity.md) 为准，交互与回放见 [Agent UI 平台边界](agent-ui-platform.md)。

## 请求、确认与账本

- 接收按 `(team_id, user_id, client_request_id)` 和请求指纹去重。同键同载荷补读原任务、轮次及结果，在检查当前等待前识别重放；同键不同载荷报冲突。提交后的持久轮次才可发 SSE `accepted`；断流不取消已受理工作。
- 写入仅由当前服务端签发的 `action_id`、`expected_version`、允许的动作和冻结载荷授权。任务按版本和预期状态原子更新（CAS）；过期、篡改、越权或不匹配的动作不写入，状态冲突返回最新投影。历史卡片只读。
- 活动确认冻结团队、用户、客户、活动类型、原文、最终稿、最终评分、`submission_id` 和载荷指纹。确认不再调用模型、不重新评分；领域写服务复核当前用户权限及目标状态。
- 活动经 `create_final_from_assistant2` 以 `ASSISTANT_2` 来源落库，`(team_id, submission_id)` 防重，复用记录必须匹配冻结指纹和目标。活动事实、冻结命令执行回执及任务结算同事务提交，不创建 AIJob 或交给旧 Agent 后处理。活动后的商机、阶段推进和任务处置各自独立；批量提交不合并各条命令事务，后续失败不撤销已成功原子。
- 商机命令调用目标服务前先持久化 `proposal_command_claim`。服务端生成 `command_id`，将团队、操作者、任务、候选、来源 revision、冻结指纹与目标绑定；阶段命令还绑定预期快照和版本。账本不是可编辑草稿，也不是成功证明。

## 目标提交归因

`crm_assistant_crm_effects` 以 `(team_id, command_id, effect_kind)` 唯一标识效果；效果和对应 CRM 事实在目标服务的同一物理事务提交。重放只认原命令、原操作者及原指纹；不同指纹或不兼容的效果类型拒绝。对账核对目标身份与预期状态，不能凭同名对象、相同操作者、常规操作日志或阶段变化推测成功。

| `effect_kind` | 权威证据 |
| --- | --- |
| `opportunity_create` | 商机 public ID 和审批实例随创建提交。已创建待审批不等于审批通过。 |
| `opportunity_stage` | 商机 public ID、原快照/版本、新阶段快照及递增版本随阶段推进提交。 |
| `opportunity_auto_won` | 自动赢单的独立后续提交；同一命令的阶段回执不证明赢单。不确定时保留已确认的阶段效果，不重推阶段。 |

正常执行只有核实目标效果后才记录 `SUCCEEDED`；有精确效果但缺助手回执时，以原命令补一次回执，claim 标为 `RECONCILED` 并退役旧等待。无归因标识的历史 claim 不补造成功。

## 错误分类与恢复

| 类别 | 处理 |
| --- | --- |
| 业务缺口、未找到、候选歧义 | 仅真实可补的缺口才补字段；歧义先选择，不凭名称杜撰或写入目标。 |
| 权限拒绝、校验拒绝、配置错误 | 不报成功或假装内容缺失。已确定不可重试的业务拒绝退役确认；明确的用户拒绝和旧阶段变化导致的跳过不是技术失败。 |
| `STATE_CONFLICT` | 补读最新权威状态，旧卡不可提交，不自动替用户确认。 |
| `RETRYABLE_DEPENDENCY_FAILURE` 等已知安全失败 | 仅在服务端允许、原任务/轮次仍匹配、版本及租约有效且幂等门禁通过时重处理原轮次。不重发原文或签发替代写入。 |
| `UNKNOWN_COMMIT_RESULT` | 可能已经提交但无足够证据；展示“结果待核对”而非成功或确定失败，保留先前的真实回执，不提供写入重试。 |

用户拒绝（`REFUSED` 语义）不是执行失败，不调用目标服务；前置条件变化且确定未调用时可 `SKIPPED`；业务拒绝且有确定未执行的证据才记 `REJECTED`。越过可能提交的边界后，不能把缺少回执当成 `SKIPPED` 或 `REJECTED`。

- 断线、刷新或迟到响应先补读原 `turn_id`（按 `after_seq`）并同步任务；若尚不知请求是否受理，按原请求键恢复，不能换键再写。任务、轮次和命令结果分开判断；租约恢复以持久状态继续，不重新解析整段对话。
- 已 `CLAIMED` 的商机命令只核对目标效果，临近或超过租约也不能自动重发。没有效果记录、读失败或无法归因不构成“未调用”证明；保留 `UNKNOWN` 或待核对，不用新卡掩盖它。没有确定未执行的证据时不得裁决拒绝；已 `STARTED` 且无法证明未提交时也一样。
- 同步/核对不是重试授权。`reprocess_allowed` 由服务端针对原轮次单独判断；正在运行的有效租约、已被更新轮次取代、活动已提交或提交未知均不允许盲目重处理。

## 命令核对权限（迁移 149）

- 迁移 [`149_assistant_command_reconciliation_permission.py`](../../../CRM-Server/migrations/versions/149_assistant_command_reconciliation_permission.py)（revision `149_assistant_command_operator`）为 opt-in 角色 `ASSISTANT_COMMAND_OPERATOR` 授予 `assistant:commands:reconcile:team`，不自动赋给团队成员或既有角色。
- `GET /v1/assistant/unknown-commands`：普通团队成员仅可查本团队自己的 `UNKNOWN`；具该权限的核对员可查本团队 `CLAIMED` 与 `UNKNOWN`。团队从登录上下文取得；列表只给命令、任务和动作引用、状态、类型和核对时间，不含客户原文或表单明细。
- `POST /v1/assistant/unknown-commands/{action_public_id}/adjudicate`：仅具该权限者可在本团队裁决未决 claim，必须记录操作者与理由。成功须有精确目标提交效果，拒绝须有确定未执行的证据；无法证明时保持待核对。裁决不授权 CRM 写入、不恢复旧卡、不重试命令。

成功裁决核对当前签名确认或冻结表单、原操作者、命令指纹与目标效果。命令标记 `RECONCILED`、旧等待撤销、精确回执追加在同一事务；仅从已有冻结队列继续。当前没有持久的确定未执行证据来源，因此 `REJECTED` 返回 409，保留待核对。

源码入口：[`turns.py`](../../../CRM-Server/app/services/assistant/turns.py)、[`confirmation.py`](../../../CRM-Server/app/services/assistant/confirmation.py)、[`proposals.py`](../../../CRM-Server/app/services/assistant/proposals.py)、[`crm_effects.py`](../../../CRM-Server/app/services/assistant/crm_effects.py) 和 [`api/assistant.py`](../../../CRM-Server/app/api/assistant.py)。本文描述现行边界，不是旧 TRD 验收记录，也不证明本次运行验证通过。
