# 客户档案彻底撤下与九类客户事实物理删除

- 日期：2026-10-10
- 状态：已批准设计，待规格审阅
- 范围：彻底移除客户档案能力，并物理删除九类非 `alias` 客户事实及其全部派生副本。
- 发布方式：一个维护窗口内停止旧进程、部署新代码、执行 Alembic 清理与删表、验证并启动新版本；不部署生产环境中间切断版本。

## 1. 目标

1. 删除客户档案 API、页面、历史、证据、刷新、重建、权限、任务、专属代码和专属数据。
2. 物理删除九类非 `alias` 客户事实，以及对应来源、修订和所有可证明的派生副本。
3. 保留 `alias` 事实，仅用于客户名称、简称、别名搜索和身份解析。
4. 保留客户、联系人、活动、活动删除墓碑、商机、合同、回款、商机旅程及事件、销售承诺、跟进任务及事件。
5. 保留由原始 CRM 数据驱动的客户问答、业务语义检索和合格 Qdrant 证据。
6. 保留独立于客户档案的初始客户补全。
7. 无法证明安全保留的派生数据默认删除。

## 2. 非目标

- 不删除客户主数据或原始 CRM 业务数据。
- 不扫描、改写或脱敏原始活动正文。
- 不删除商机自身的销售阶段字段。
- 不把 `alias` 注入客户问答上下文。
- 不整体删除共享客户智能 Graph、运行表、checkpoint 表、Agent memory 表或向量表。
- 不使用 Alembic `downgrade` 恢复已删除业务数据。
- 不使用 `alembic stamp`、手改 `alembic_version`、手工 SQL 绕过或恢复未经批准的 dangling commit。
- 不修改共享 `crm-mysql-dev` 的数据、迁移、DDL、测试写入或运行状态。
- 不修改 `CRM-Server/.env`，不覆盖现有 dirty worktree 变更。

## 3. 删除与保留边界

### 3.1 删除的九类事实

- `need`
- `budget`
- `risk`
- `stage`
- `stakeholder_attitude`
- `competitor`
- `next_step`
- `preference`
- `summary`

删除覆盖：

- `crm_customer_facts` 中九类记录；
- 对应 `crm_customer_fact_sources`；
- 对应 `crm_customer_fact_revisions`；
- Store 事实索引、偏好区段和叙述性摘要；
- customer intelligence run 与 checkpoint 中的对应 payload；
- 实际复制九类事实且无法由允许的原始 CRM 对象重建的向量文档和 Qdrant point。

### 3.2 保留能力

- `alias` 事实、来源和修订；
- 客户身份解析与别名搜索；
- 客户、联系人、商机、合同、回款；
- 活动、活动删除墓碑；
- 商机旅程及事件；
- 销售承诺；
- 跟进任务及事件；
- 原始 CRM 数据驱动的客户问答；
- 业务语义检索与合格 Qdrant 证据；
- 独立于客户档案的初始客户补全。

`alias` 只服务身份能力，不得进入问答上下文，也不得被当作客户事实回答。

## 4. 用户可见行为

### 4.1 客户档案路由

所有旧客户档案路由返回 HTTP `410 Gone`：

```json
{
  "code": "CUSTOMER_PROFILE_REMOVED",
  "message": "客户档案能力已移除"
}
```

处理约束：

- 在客户查询、团队查询、档案表查询和档案权限检查之前返回；
- 不因客户不存在、无权限或已删除而返回不同错误；
- 不泄露客户 ID、业务 ID 或档案存在状态；
- 档案刷新、重建、历史、证据和变更接口均适用；
- 其他保留客户接口继续使用原有权限和不存在/无权限语义。

### 4.2 客户问答

问答只使用客户、联系人、商机、合同、回款、活动、活动墓碑、商机旅程及事件、销售承诺、跟进任务及事件，以及合格业务证据。

问答不得读取九类事实、客户档案投影、历史档案版本、客户事实索引、偏好、叙述性摘要或已删除事实的长期引用。

无允许范围内的原始 CRM 证据时，返回“现有 CRM 信息不足”，不得根据旧事实、摘要或模型常识补全。商机原始销售阶段仍可回答，它不属于被删除的客户事实 `stage`。

### 4.3 活动与初始补全

活动创建、更新、删除墓碑和事务提交不依赖 `intelligence_request_id` 或档案提炼回执。customer intelligence 异步失败不回滚已提交的 CRM 主事务。

保留独立于客户档案的初始客户补全；删除 profile-only wake-up、档案刷新、档案发布和九类事实提炼、提案与持久化。

原始活动正文中自然出现“预算”“需求”“风险”等词时，不删除、不改写、不脱敏。

## 5. 代码边界

### 5.1 删除档案专属实现

删除客户档案 API、Schema、模型、CRUD、projection service、projection Graph、evidence resolver、version certification、watermark service、legacy source service，以及档案专属任务和权限。

前端删除客户档案页面、入口、API client、store、权限判断和相关展示。

### 5.2 收缩共享客户智能 Graph

保留共享 Graph 中客户问答和业务证据路径，删除：

- 九类事实 extraction、assessment、persistence；
- profile refresh route；
- 叙述性摘要写入；
- 事实索引和偏好写入；
- profile-only trigger 处理。

活动、联系人、业务对象、旅程和任务等原始 CRM 事件继续保留，但不得重新触发九类事实写入或档案投影。

### 5.3 收缩上下文、提案与运行摘要

客户上下文删除：

- 全部九类事实读取；
- `CustomerLegacySourceProgress` 查询；
- 事实进入 source snapshot 和 watermark 的路径。

Agent proposal contracts 和 CRM proposal command 删除 `customer_fact` 九类提案能力。若 alias 提案不是当前已批准的身份维护能力，则不在本次扩展；本次目标是关闭九类事实提案，而不是新增 alias 管理能力。

运行摘要只保留状态、错误、重试、安全证据引用和保留能力所需诊断；删除 profile version、publication、fact changes、事实引用、事件正文和含事实的 trace payload。

### 5.4 Scheduler

新版本不得启动：

- 客户档案刷新重试；
- 客户档案历史回填；
- 客户智能档案对账；
- 档案专属重建或发布任务。

保留客户证据同步及其他无关 CRM 任务。旧档案队列项和可恢复运行必须清理或标记为不可执行，新版本不得再次领取。

## 6. 共享数据清理矩阵

| 对象 | 保留 | 删除或清理 |
|---|---|---|
| `crm_customer_facts` | `alias` | 九类非 `alias` 事实 |
| `crm_customer_fact_sources` / `crm_customer_fact_revisions` | `alias` 对应记录 | 九类事实对应记录 |
| 客户档案三张表 | 无 | 整表删除 |
| `crm_customer_legacy_source_progress` | 无 | 整表删除 |
| `crm_agent_memory_entries` | 校验通过的 `retrieval` 证据引用 | `facts`、`preferences`、`summaries`，以及含正文、事实、摘要、偏好或不明字段的 retrieval |
| `crm_customer_intelligence_runs` | 服务问答、业务证据和其他保留流程的安全审计记录 | 纯档案运行；保留记录中的档案字段、事实引用、事件正文和含事实轨迹 |
| LangGraph checkpoint 三表 | 表结构及其他安全 CRM/Agent workflow checkpoint | 档案 workflow checkpoint；含禁止 payload 或无法安全分类的客户智能 checkpoint 及其 blobs/writes |
| `crm_customer_vector_documents` 与 Qdrant | 可从允许的原始 CRM 对象重建的业务证据 | 档案、Agent 判断、无法重建或来源不明的文档及 point |

### 6.1 客户事实

`crm_customer_facts` 表保留。迁移后应用层只接受 `alias`，数据库层增加 alias-only 防护。删除客户事实不删除活动、商机阶段、`next_action` 或其他原始 CRM 字段。

### 6.2 Store

客户记忆不再持久化客户画像：

- `facts` 全部删除；
- `preferences` 全部删除；
- `summaries` 全部删除；
- `retrieval` 只保留来源类型、业务对象标识、证据键和分数等结构化引用。

包含正文、事实引用、摘要、偏好、引语或无法分类字段的 retrieval 条目删除。新 Graph 只写入安全业务证据引用。

### 6.3 Runs 与 checkpoint

纯档案刷新、重建、回填和对账运行删除。保留的问答和业务证据运行收敛为不含事实正文、档案版本、事实引用和事件正文的安全摘要。

客户智能 checkpoint 使用现有安全反序列化检查器逐个分类。只要包含禁止字段、事实上下文、档案 draft，或无法安全解码，就删除该执行身份下的 checkpoint、blob 和 write。其他 CRM 活动、任务、承诺和确认工作流 checkpoint 不受影响。

无法安全证明的数据不做关键词擦除后保留，而是删除整个执行身份。

### 6.4 Vector 与 Qdrant

允许保留的来源类型：

- `business_flow`
- `follow_up`
- `follow_up_task`
- `sales_commitment`

保留文档必须同时满足：

1. 来源对象存在或具有合法删除状态；
2. 当前证据构建器可由原始 CRM 对象重新构造；
3. 重建后的正文哈希和元数据符合当前规则；
4. Qdrant point 与 MySQL metadata 一致。

不按正文关键词删除。provenance 指向已删除事实、档案投影、Agent 判断，或无法由允许对象重建时，删除 MySQL metadata 和 Qdrant point。

## 7. 迁移与发布

### 7.1 Revision 前置门禁

隔离副本记录 `151_assistant_proposal_policy`，当前 checkout head 为 `150_profile_version_attestation`。清理前必须：

1. 从合法、已批准的仓库来源恢复 `151_assistant_proposal_policy`；
2. 校验其 `down_revision`、迁移内容和仓库历史；
3. 在隔离副本执行 `alembic current`；
4. 执行 `alembic upgrade head` 并确认链完整；
5. 找不到合法 revision 时立即停止。

禁止 `stamp`、手改版本表、手工 SQL 绕过和恢复未经批准的 dangling commit。

### 7.2 维护窗口顺序

1. 创建并验证发布前备份。
2. 在隔离副本预演同版本代码、迁移和清理。
3. 执行只读门禁，确认旧进程已停止。
4. 停止旧 API、worker、scheduler。
5. 部署已切断档案写入路径的新代码。
6. 执行 Alembic 准备迁移。
7. 执行受控 Qdrant 删除同步并验证 point 不存在。
8. 执行 Alembic 完成迁移。
9. 验证数据库结构、残留和保留数据。
10. 启动新 API、worker、scheduler。
11. 执行启动后 smoke check。

Qdrant 删除不在数据库事务内。Qdrant 删除或验证失败时不得执行完成迁移，保留 `DELETE_PENDING` 以便重试。不得先删除 MySQL metadata 再猜测 Qdrant 状态。

### 7.3 准备迁移

准备迁移负责：

- 校验当前 Alembic revision；
- 删除九类事实来源、修订和主记录；
- 清理 Store、run、checkpoint 中不允许保留的数据；
- 将目标向量文档标记为 `DELETE_PENDING`；
- 删除不依赖外部系统确认的档案专属数据；
- 保留完成迁移所需的目标删除清单和验证证据。

### 7.4 完成迁移

完成迁移仅在目标 Qdrant point 已验证删除后执行：

- 删除目标 `crm_customer_vector_documents` 行；
- 删除客户档案三张表；
- 删除 `crm_customer_legacy_source_progress`；
- 删除失效外键、索引和数据库对象；
- 保留共享 runs、checkpoint、memory 和 vector 表。

档案表内部先处理 `crm_customer_profile_current`，再处理 `crm_customer_profile_projection_versions`，并解除其对 `crm_customer_intelligence_runs` 的外键依赖。

### 7.5 失败边界

- 准备阶段失败：停止并保留现场，修复后从明确阶段重试。
- Qdrant 阶段失败：不执行完成迁移，修复后重试外部删除。
- 完成阶段结构性失败：停止服务，不盲目重复执行，依据备份和迁移证据做前向修复或恢复。
- 不使用 Alembic downgrade 恢复已删除业务数据。

MySQL DDL 可能隐式提交。发布依赖备份、隔离副本预演、迁移证据和前向修复。

## 8. 回退边界

- 破坏性迁移前失败：恢复旧代码和旧进程，不修改数据库。
- 档案表删除后：不得启动旧版本；旧档案数据只允许恢复到隔离实例，不回灌生产。
- Qdrant point 删除后：只从保留的原始 CRM 数据和当前证据构建器重建允许的业务证据。
- 新版本 smoke check 失败：保持新版本停机或隔离，修复后重新验证；不得回退旧应用绕过已删除 schema。

## 9. 验证矩阵

### 9.1 发布前

- 备份成功且隔离副本可读取；
- `151_assistant_proposal_policy` 合法存在；
- Alembic revision 与目标 head 符合预期；
- 旧 API、worker、scheduler 已停止；
- 迁移前脱敏计数已记录；
- Qdrant 删除清单与 MySQL 目标集合一致。

### 9.2 结构与残留

验证：

- 三张档案表和 legacy source progress 表不存在；
- 不存在指向已删除档案表的外键、索引、ORM import、schema 或任务注册；
- 非 `alias` 客户事实为零；
- `alias` 事实、来源、修订保留；
- 九类事实来源和修订为零；
- Store 的 `facts`、`preferences`、`summaries` 无残留；
- 保留 retrieval 只含合格业务证据引用；
- runs、checkpoint、blob、write 无档案或九类事实 payload；
- 禁止保留的 vector metadata 和 Qdrant point 不存在；
- 保留 vector metadata 与 Qdrant 状态一致；
- 原始 CRM 表、活动墓碑、任务、承诺、旅程、商机、合同和回款未被误删。

扫描输出只包含计数、哈希和通过/失败状态，不输出正文、客户 ID、source ID、文档 key、citation 或向量内容。

### 9.3 启动后

至少验证：

1. 每类旧 `/profile` 路由返回 `410/CUSTOMER_PROFILE_REMOVED`；
2. handler 未访问客户或档案表；
3. alias 搜索和身份解析成功；
4. 无证据时客户问答返回信息不足；
5. 原始商机、合同、回款、活动、旅程、承诺和任务仍可回答；
6. 业务语义检索返回合格 Qdrant 证据；
7. 活动创建、删除墓碑和 post-commit 成功；
8. 初始客户补全成功；
9. 档案 scheduler 未注册、未启动、未领取旧任务；
10. 新运行不会写入九类事实、档案投影或禁止 Store 区段。

## 10. 实施顺序

1. 合法修复 Alembic revision 链。
2. 解除活动 receipt 强依赖。
3. 移除共享上下文中的九类事实和 legacy progress 依赖。
4. 收缩 Graph、Store、proposal、run summary 和 scheduler。
5. 将旧档案路由改为 `410` tombstone，并删除前端入口。
6. 删除档案专属代码、权限、模型和注册。
7. 编写 Alembic 准备迁移与完成迁移。
8. 在隔离副本预演数据库清理和 Qdrant 删除。
9. 执行发布验证矩阵。

实施不得扩展到无关 CRM 能力，也不得把名称包含 `intelligence` 的共享对象整体删除。

## 11. 验收不变量

1. 客户档案路由始终返回统一 `410`，且不产生信息差异。
2. 九类事实无法读取、写入、提案或重新进入 Store、run、checkpoint。
3. `alias` 保留且不进入问答上下文。
4. 原始 CRM 数据继续驱动问答和业务检索。
5. 活动事务独立于档案回执和异步智能任务。
6. 初始客户补全独立于档案刷新。
7. 无法证明安全的派生数据被删除，而不是猜测保留。
8. Qdrant 删除完成前不删除对应 MySQL metadata。
9. 已删除业务数据不依赖 downgrade 恢复。
10. 所有验证输出保持脱敏。
