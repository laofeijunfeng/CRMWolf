# 销售助手 Agent 2.0 七项优化 TRD（实施与验收证据）

- **版本：**2026-09-30 目标设计；2026-10-01 实施及隔离验收证据；2026-10-02 至 2026-10-03 复核 §9–§10；2026-10-08 §9.9 补当前源码四类修复与同链验收。§1–§8 的“现状／代码路径可判定”是改造前基线，§9 各节仅证明各自时点和指定运行版本，不能把历史运行态混作当前源码；§10 为发布门禁判定。本文不代表已获产品、安全或生产发布批准。
- **范围：**仅销售助手 Web `/assistant` 与后端 `/v1/assistant`，以及这条链路实际触达的旧客户智能读取／发布边界和 CRM 命令边界。旧 Web Agent、飞书 IM、页面表单不切换；不创建客户、线索、回款或合同。
- **优先合同：**[`CONTEXT.md`](../../../CONTEXT.md) 第 15–44 行和 Accepted [`docs/adr/0001-customer-activity-workflow-parity.md`](../../../docs/adr/0001-customer-activity-workflow-parity.md) 第 16–54 行。本文细化其 2.0 入口规则，不推翻活动新增／删除、最终评分一次保存、下一步行动门禁、提交后独立处理及商机独立原子。界面实现另遵循 [`CRM-Docs/design-system/README.md`](../../design-system/README.md)。
- **关系：**新增的专题 TRD；不替代、不改写 [`agent-2-optimization-trd.md`](agent-2-optimization-trd.md) 和 [`agent-2-round3-optimization-trd.md`](agent-2-round3-optimization-trd.md)。旧文档的代码“现状”和测试结论有历史时点限制；本文件的当前实现以以下代码路径为准，不将原草案里的旧缺口继续算作今天的缺口。

## 0. 证据边界、总目标及不变量

下文使用三个不同等级；**目标合同／验收场景均不是已验证事实**。

| 等级 | 含义 | 本轮可陈述的事实 |
| --- | --- | --- |
| **已复现** | 实际运行一次性探针并观察数值，不扩大推论 | 前序一次性 SQLite 探针：增添 2.0 活动及其旅程事件后，旧上下文活动数量 `1→1`、合格旅程事件数量 `0→0`，`latest_journey_updated_at` 却由 `2026-09-30T12:52:39.045246` 变为 `2026-09-30T12:52:39.070925`。只证明共享聚合时间影响旧水位；**没有证明最终档案发表了 2.0 正文**。不以此代替 MySQL 并发测试。 |
| **代码路径可判定** | 当前函数的分支、数据库提交位置或接口形状足以确定条件下的行为；未必有运行时复现 | 例如 2.0 在已有恰好一个未结束旅程时会写 `activity_added`，前端活动专用 payload schema 不接收提案 payload，`unknown-commands` 不校验本人权限；参见各节定位。 |
| **尚未复现的条件风险** | 需要并发时序、历史数据或权限变化触发，尚无端到端证据 | 例如旧草稿在来源改变后覆盖新事实、第三方同名商机或阶段变更被误认作本命令成功、删除后 NULL 外键的历史来源误判；必须用指定双会话／历史数据场景验证。 |

**总体交付结果：** 2.0 的活动原文与最终稿可审计；每一笔活动、商机创建、商机阶段推进及后续任务／事实各有独立授权和可恢复结论；旧客户智能仅看其获准来源；页面刷新、断流和任务切换不会猜测状态。模型只能提名候选和辅助整理，不得直接改权威任务状态或写 CRM。不得以“请求成功”“存在同名对象”“阶段已变化”代替某条命令的目标提交回执。

**保留且复用的底座：** `AssistantRequest` 按 `(team,user,client_request_id)` 去重；`AssistantTurn` 持久化、租约与恢复；任务条件更新／版本 CAS；签发的等待 `action_id` 和 `expected_version`；冻结活动命令中的 `submission_id`／指纹；独立的活动事实提交。实现分别见 `CRM-Server/app/services/assistant/turns.py:82-199,326-469`、`task_state.py:108-204`、`confirmation.py:42-147`。不另造一个横跨活动、商机和阶段的事务。**不得**在确认时再次调用模型或评分；实体写入只有最终评分且 `score >= 60`，下一步行动缺失／模糊时独立追问，明确无下一步必须有原因或复查条件；2.0 字段局部合并，最终稿实质变化则重评分（ADR §1、§2、§4、§7；`CONTEXT.md:18-25,30-44`）。

七项依赖顺序：**① 来源视图／发布边界**和**③ 目标提交归因**是安全底座；**② 候选＋表单**依赖③的写入协议；**④ 确定拒绝／待对账**依赖③的效果回执；**⑤ 客户端协议**消费②④；**⑥ 原文更正**决定①②可执行证据；**⑦ 运维／日期**横切②④⑥。可以分批开发，不能在缺归因时打开商机创建按钮。

## 1. 优化一：2.0 来源、旧客户智能投影和水位彻底隔离

> **2026-10-10 批次作废：**客户档案能力已整体移除（设计 `docs/superpowers/specs/2026-10-10-customer-profile-removal-design.md`；分支 `codex/customer-profile-removal` 合入 main）。投影、水位、发表栅栏、legacy source progress、`/profile` API、三张档案表已物理删除（Alembic 152/153）。本节 §1.1–§1.3 与 §9.1 S01–S09、§10 A 批次的“旧档案发表”目标不再存在，保留原文仅作历史基线。仍然有效的残留边界只有一条：2.0 活动及其派生不得流入旧客户智能读取路径——该边界在档案移除中已由“上下文不再读取客户事实 + 证据检索保留 `eligible_activity_source` 过滤 + `legacy_profile_source` 仅存 origin/provenance 判定”实现，并有 `test_customer_intelligence_context_service.py` 等回归覆盖。A 批次门禁据此改判：**档案侧无遗留验收条件**；B/C/D 批次条件不变。

### 1.1 现状与证据

**代码路径可判定：** `assistant/real_writer.py:51-83` 把活动标为 `ASSISTANT_2` 且不直接排旧智能刷新；`app/crud/customer_activity.py:237-278` 在**已有恰好一个非 LOST／COMPLETED 旅程**时可写 `activity_added`，不会因为该活动单独创建新旅程。`deal_journey_service.py:327-411` 更新共享 `CustomerDealJourney.last_event_at`。旧 `customer_intelligence_context_service.py:476-620,798-936` 过滤部分 2.0 活动／tombstone／事件，却序列化共享旅程聚合并将聚合时间计入水位；投影 `customer_profile_projection_service.py:1457-1570` 使用聚合的时间及排序。因此“没直接入队”不等于“没有间接改变旧投影输入”。上述 SQLite 水位变化**已复现**，正文被实际发表**未复现**。

**代码路径可判定的其他缺口：** 水位从排序后 `LIMIT` 的展示列表推得，可能漏掉窗口外最大的合格来源 ID（`customer_intelligence_context_service.py:476-637,883-936`）；事实过滤只查直接活动来源，不足以证明经 `deal_journey_event`／`business_flow` 间接归因的事实（`customer_fact_service.py:320-386`）。任务／承诺源活动被删除后外键可 `SET NULL`，但仍有 `source_type/source_key` 等线索（`app/models/sales_commitment.py:166-180,245-257`）。`/profile/evidence` 对已存引用的读取只检查对象和团队／客户，不追来源（`api/customer_profiles.py:229-253`；`customer_profile_evidence_resolver.py:89-177,209-215`）。partial 草稿会继承旧段落及引用，去重发表也能移动当前指针并设 READY（`customer_profile_projection_service.py:188-249,469-505`）。

**尚未复现的条件风险：** A 取旧快照、B 写合法来源／删除后 A 发旧稿；当前 publish 比候选与 `current.latest_source_watermark_json`，不在发表时重新锁定来源快照（`customer_profile_projection_service.py:393-560`）。`mark_stale` 会**覆盖**已知水位（`:374-391`），普通事件只写稀疏元数据（`customer_intelligence_refresh_service.py:897-909`）；不能据此声称删除必然永久卡死，亦不能声称“2.0-only 客户绝不会被旧回填扫描”：历史回填资格会计入任意来源活动（`:1688-1704`）。可保证的是**合格内容与来源进度不混入旧档案**，不是禁止所有旧扫描。

### 1.2 单一来源政策

为旧客户智能定义版本化 `LEGACY_PROFILE_ELIGIBLE_Vn` 来源判定，以 `(team_id, customer_id, origin_kind, origin_id, source_revision)` 为作用域；**当前政策下所有 `ASSISTANT_2` 活动及其派生事件、事实、任务、承诺、向量命中和删除 tombstone 均不得进入旧档案**，不得因有其他合法来源的同一旅程整行隐藏或整行放行。将来若要改变授权范围须另行批准、升来源策略版本、回填并重新验收，不能用某次“创建商机”确认授权旧档案发布。追溯到同团队同客户的活动行或带来源 tombstone；沿 `customer_activity → deal_journey_event/business_flow → fact/evidence/task` 追链。`source_activity_id IS NULL` **不证明**独立来源：先检查 `source_type/source_key/source_public_id` 及 tombstone；既不能因删除丢弃合法历史证据，也不能将来源不明的旧引用当合格。来源不可确定时在旧投影**失败关闭**，记录非敏感原因；2.0 自身的 canonical 活动、事件和证据依旧保留并按 2.0 自己的权限可见。

旅程**不能整行按是否碰过 2.0 活动隐藏**：现有合法业务属性、合格旧事件要保留；用合格事件／有明确独立来源的业务变化计算旧视图 `legacy_last_event_at`、排序、事件摘要及相关 freshness。原共享 `last_event_at/updated_time` 只供原领域使用，不自动取得旧投影资格。仅由不合格来源形成、且无其他可证明合法业务状态的旅程不展示；混合旅程显示合格部分。无法还原某客户合格旅程／来源链时，拒绝**该客户**新档案发表，保持上一个经核验可读的版本；不能因此拦截其他客户的合法刷新。

统一政策进入：上下文读取（先过滤再排序／`LIMIT`）、候选事实持久化、语义检索、草稿引用及 partial 继承、发表、全量对账／历史回填，以及已存引用的**读时**证据解析。对历史版本中来源不合格或来源未知的证据，`/profile/evidence` 返回 `UNAVAILABLE` 且不泄露摘要／链接；若旧正文也已被污染，按受影响客户隔离／重建现行版本，不修改不可变历史版本。来源授权不能通过用户确认“创建商机”暗中扩大为授权旧客户智能发布。

### 1.3 进度、水位与发表栅栏

把**展示窗口**和**来源进度**分开：独立查询完整合格来源集合的变更（活动、tombstone、旅程合格贡献、事实、任务、承诺、可核验证据），使用按客户的持久单调 `eligible_revision`／删除进度及来源策略版本作权威比较；显示列表仍允许 50／100／200 条上限。当前存活对象 `MAX(id)` 是快照诊断，不是单调进度：删除 ID=N 后，`activity_id` 可以下降而删除进度上升；不能逐字段 `MAX` 合并覆盖删除。稀疏事件键／触发类型是调度元数据，不允许替代完整来源进度；首次／全量对账扫描必须按客户 ID 翻完页，不能仅观察第一批或以 `LIMIT` 展示数算已处理数（`customer_intelligence_reconciliation_service.py:93-238`；`customer_profile_watermark_service.py:29-86`）。

每个能改变旧投影合格视图的**源写／删除／资格更改**，与该客户单调进度推进在同一提交边界，并参与同一客户级串行化栅栏；如果当前写入口无法保证覆盖，先禁用该入口的发表，不能只在 publish 末尾做一遍无锁 SELECT。草稿冻结 `(team,customer,policy_version,eligible_revision,source_snapshot_hash,current_profile_version,run_id,owner)`。发表和所有去重／继承分支在同一客户锁或等价 CAS 下重新计算合格来源进度和引用资格，检查运行 owner、当前指针与草稿一致，随后才插版本／切指针／设 READY。若 B 先于 A 发表提交了合法源，A 拒绝并保留原指针与可读版本；若 B 在 A 发表后提交，B 必须按同一串行化顺序推进进度并标脏／排刷新。只有 2.0 变化不推进**旧合格**进度；共享旅程不能绕过。失败/不明链保留客户可读的既有**合格**版本并告警，不把单个客户故障扩散为全库停止。

历史切换只新增 Alembic 所需的进度／归因字段和可重跑的按团队客户回填；记录扫描水位、策略版本、合格／未知来源计数、拟重建和拒绝发表客户数。先影子计算旧／新差异，再针对污染或不确定版本按来源隔离重建；不把旧版 provenance 不明伪装成已通过。回滚到旧逻辑会重新暴露已知来源漏洞，因此只允许**停止新旧档案发表、保留受控可读版本并恢复安全读时门禁**，而不是撤掉门禁；保留 2.0 活动事实和不可变版本。

## 2. 优化二：真实商机候选、Agent 页内嵌补字段和逐笔创建

### 2.1 现状与证据

**代码路径可判定：** `assistant/proposals.py:39-62` 读可选 `authority_json.proposal_candidates`，否则仅从已存活动内容合成客户事实／行动项候选；已审查的生产 2.0 路径未发现写商机候选的生产者。旧商机建议 job 面向旧 `AGENT` 来源及旧界面，不可当作 `/v1/assistant` 的供给（`customer_opportunity_suggestion_job_service.py:102-124,536-548`）。创建校验在提案前已要求完整 `OpportunityCreate`，且金额、人数、预计成交日期逐字位于原活动文本（`assistant/crm_proposal_commands.py:215-240`）；这与“先问是否创建、再在 Agent 内补值”矛盾。`SubmitInputRequest` 只有 text／choice，没有结构化字段（`api/assistant.py:69-78,336-363`）；`ProposalCard.vue:1-67` 仅有确认／拒绝按钮。`OpportunityCreate` 硬约束金额／人数 >0、授权与采购类型、日期、产品与至少一模块；订阅制必须有正的年限，商机名可不填（`app/schemas/opportunity.py:106-145`）。本节缺口属代码路径可判定，**不声称已跑过真实表单路径**。

### 2.2 候选、提议、表单、冻结命令分层

1. **候选生成：**活动提交后，独立持久 turn 读取**最终 canonical 活动＋仍有效的用户原话**。模型只建议采购信号及引用；服务端验证引用段 ID／准确原话／语义有效项、客户绑定、活动 revision、权限和 CRM 最新数据。不从通用旧建议 job 直接复用状态。无信号不问；能高置信度匹配同客户现有商机时**静默去重**；不确定同名／目标不唯一时不能静默创建或凭名称推断唯一，可追问目标或按无安全候选处理。阶段建议必须绑定特定商机、当前有效采购方式／相邻阶段与原活动阶段证据。每次只显示一笔真实候选，后续候选由独立 turn 签发。
2. **身份拆分：**`candidate_id` 从 `(team,customer,activity_id,activity_revision,signal_segment_id,semantic_target,kind)` 形成稳定不可变值；`form_revision` 随填表更新；`command_id`／`command_fingerprint` 在最终表单和 target 快照冻结**后**确定。当前 `_candidate_key` 含整个 payload，填表会改变身份（`proposals.py:30-36`），须切开。候选标识不是 CRM 幂等键；同候选不同冻结载荷不可重用同命令 ID。
3. **双阶段授权：**签发 `proposal:opportunity_create` 的展示 wait 只询问“是否创建”，并展示来源语句、目标客户、已有商机去重理由。拒绝记 `REFUSED`，活动不回滚；接受只是进入同一 proposal 的 `FORM_DRAFT`，**不是创建授权或成功回执**。在 Web `/assistant` 中渲染轻量内嵌表单（沿用字段规则和选择器，不调用旧重型 `OpportunityFormDialog` 的直接创建 API）；服务端发同团队授权客户、产品／模块、采购方式／阶段等合法选项，`owner_id` 与客户 ID 不信任前端自由填值。所填金额、人数、成交日期等标为**用户在表单提供的新证据**，不要求原活动逐字出现；原文只证明购置信号及被引用的事实。客户端填值不自动意味着“已经写入”。
4. **提交表单：**接受展示 wait 后由服务端签发同一 `candidate_id` 的**新表单 wait** 和新任务版本；新增专用 `submit_opportunity_form` 输入（结构化 Pydantic schema），携**当前表单 wait** 的 `action_id`、`expected_version`、`client_request_id`，不能重用已经消费的展示 wait 凭证。任务版本 CAS、本人／团队鉴权、候选 ID、当前产品模块关系、`OpportunityCreate` 完整约束、活动 revision、CRM 权限／审批流再验；无效字段返回稳定字段错误和仍可编辑的新版本表单等待，不产生 claim／CRM 写。合法提交冻结 `team/user/customer/activity/revision/candidate/form/source_evidence/command_id/fingerprint`，通过**第三节**的目标提交归因执行；表单确认权只覆盖这笔商机创建，不授权阶段推进、活动修改、客户事实或档案发布。重复同键同载荷补读原 turn；同键改值 409；旧 wait／跨用户／跨团队不可提交。
5. **阶段独立：**`opportunity_stage` 有自己的候选、签发等待、目标快照／版本与命令；绝不把创建＋推进合为一笔。确认时若提议后阶段／版本已变化，按 ADR **静默跳过**，不得再推进、覆盖新状态或要求用户重按旧卡。其余权限、采购方式及目标阶段重校验，不用“最新阶段不是旧阶段”冒充本命令成功。

呈现必须区分“活动已写入”“是否创建商机”“正在补字段”“该商机创建已确认且结果待核对”“这笔商机已创建／被拒绝／被跳过／确定失败”；单个后续命令的失败不会把已成功活动或更早原子回滚。表单 UI 遵守设计系统语义色、错误反馈、键盘和窄屏布局；卡片刷新时从服务端投影恢复草稿与当前签名等待，不调用 `opportunityApi.createOpportunity` 绕过助手机制。

## 3. 优化三：跨事务 CRM 命令归因，不能按相似状态猜成功

### 3.1 现状与证据

**代码路径可判定：** `assistant/proposals.py:153-227` 在调用 CRM 前将 `CLAIMED` 单独提交；`readback_outcome():99-130` 在重试时只以同客户同名商机或“阶段快照变了”判成功。名字可能不提供、自动生成（`crud/opportunity.py:459-470`），同名也不证明归因。通用 `crm_command_executions` 已存在（`models/command_execution.py:14-51`），但助手链未接入，且简单在助手外层写它**跨不过**目标内部的 `commit()`：商机创建由 `approval_transaction_manager.py:69-163` 提交，阶段在 `crud/opportunity.py:673` 提交，100% 自动赢单再在 `:694` 提交。

第三方恰好同名创建、另一个操作者推进阶段后被误判成功，属于**尚未复现的条件竞态**；上述代码只能证明现有读回**不足以证明该命令造成了变化**，不能宣称已经发生具体误归因。阶段读校验与提交之间若别处改变版本也需真实并发验证；CRM 原有操作日志／旅程事件有对象与 actor，不等于持有本次助手的 `command_id`。

### 3.2 目标提交边界的相关回执

服务端生成不可由模型／客户端指定的 `command_id`，在命令 claim 中持久绑定 team、actor、task、proposal/candidate、冻结参数指纹、活动 revision、目标及其旧版本。目标 CRM **同一物理提交**中写入受唯一约束 `(team_id, command_id, effect_kind)` 的不可变相关记录：`effect_kind=opportunity_create` 绑定新商机 public ID／审批实例，或 `effect_kind=opportunity_stage` 绑定目标 public ID、新 `OpportunityStageSnapshot.id` 与旧快照／版本。重复同命令 ID 先按指纹比对并返回原相关效果；不同指纹冲突。CRM 目标写入之前检查数据库锁／版本和当前权限；不能仅凭应用层先查再无条件覆盖。把 2.0 命令上下文传进真实 CRM **应用服务的提交层**，在 `create_with_approval` 内部 commit 前落归因，或重构成等价的无内层 commit 原子；在 `move_to_stage` 的第一提交前落阶段归因。不能只把 ledger 放在助手调用者外面，不能把一般审计／同名对象当作提交证明。

100% 阶段路径的“阶段已提交”和“自动赢单已提交”分属两个提交；第二次提交也需 `effect_kind=opportunity_auto_won` 的唯一相关效果及其自己的成功／待核对状态。若第一提交成功、第二失败或响应丢失，报告**阶段确已推进、赢单效果未证实／待核对**，不得把整条路由宣称原子成功或重跑阶段；后续修复赢单只能遵循其单独幂等领域规则。操作日志／通知失败亦不能改写已提交效果的事实。

状态与崩溃顺序：

| 位置 | 服务端允许的结论 | 恢复动作 |
| --- | --- | --- |
| claim 之前验证拒绝 | `REJECTED` 或旧阶段变化 `SKIPPED`，未调用目标 | 退役旧等待；保留活动与此前效果。 |
| `CLAIMED` 已持久、目标尚未调用且可证明未跨提交边界 | `REJECTED`／`SKIPPED`，记录确定无效果证明 | 退役 continuation；不能模糊转 `UNKNOWN`。 |
| 已进入可能提交的目标事务、响应丢失／进程死于目标提交后 | `CLAIMED` → 对账到 `SUCCEEDED`／明确无效果 `REJECTED`，否则 `UNKNOWN` | **只读**查询 `(team,command_id,effect_kind)` 相关效果；不重发 CRM 创建／推进。 |
| 目标相关效果在事务内可见、助手回执未写 | `SUCCEEDED` 可核对，指向精确对象／快照 | 写一次助手收据与命令状态；同键重复只返回原收据。 |
| 只看见同名对象、相同 actor、阶段改变或缺少老历史 claim 的相关 ID | **不能**作为归因成功 | 保持 `UNKNOWN`，需获授权的人工核对；无证据时不得自动“修复”为成功。 |

旧 `CLAIMED/UNKNOWN` 记录无 `command_id` 目标关联，迁移后仍为未证实历史，不补造成功回执。存量扫描、人工裁决、事件审计与新命令格式应区分 `legacy_unattributed`；人工确认老命令成功必须有可独立核验的一对一目标提交证据，否则保持未知，相似状态不是证据。此变更需要 Alembic 约束／回填和唯一冲突演练；发布前证明 MySQL 双会话同命令、目标提交后断电重启、一商机同名第三方创建、阶段并发变更及 100% 分段提交的真实效果。

## 4. 优化四：`CLAIMED` 对账、确定拒绝与未知提交分流

**现状（代码路径可判定）：** `assistant/proposals.py:169-209` 提前提交 claim，而在执行器复验失败时下一次会尝试不具归因的读回；当前未证实即转 `UNKNOWN`，可能把明确权限／版本／表单／审批拒绝混成待人工对账。`list_unresolved_command_claims():255-279` 只返回 `UNKNOWN`，**滞留 `CLAIMED` 不在列表**。`approval_transaction_manager.py:90-95` 在要求审批且无审批流时可回滚；不过进入任何可能已内部提交的路径之后收到异常，都不能仅凭异常文本断言未写。

**目标为正交两层状态：**任务 `ACTIVE/COMPLETED/CANCELLED/FAILED`、turn `PENDING/RUNNING/SUCCEEDED/FAILED` 保持现有语义；另外给每笔业务命令 `OFFERED/FORM_DRAFT/FROZEN/CLAIMED/SUCCEEDED/REFUSED/REJECTED/SKIPPED/UNKNOWN`，限定合法转换，记录 `last_checked_at`、目标效果及错误码。`REFUSED` 是用户成功拒绝，`SKIPPED` 是有证明的状态变化不执行，`REJECTED` 是命令确未执行的业务拒绝，`UNKNOWN` 是可能已提交但缺归因证据；**turn FAILED 不代表活动失败，任务 ACTIVE 不代表可重新提交当前命令**。

在签发提案、表单提交、冻结、claim 前分别做便宜且确定的校验；目标应用服务还须在自己的真实提交边界复核。若 CRM 调用前或事务已**确定回滚**，用户权限被撤回、源 revision 改变、表单缺字段、审批流不匹配等，记持久 `REJECTED` 并退役当前 `action_id`／确认 continuation，返回精确可行动错误；有适用的用户可修复表单场景则保持 `FORM_DRAFT` 并签发**新版本**的填写等待，不保留旧可确认卡。已签发阶段提案后商机变化按 ADR 记 `SKIPPED` 并静默进入下一笔/完成。无论哪一种，已经成功的活动／其他命令不回滚；未来重试必须是新任务或全新合法提案，不得重放已成功 create。

在 claim 后一旦无法证明目标未提交，先按第三节目标回执对账；若目标回执缺失、数据库不可达、凭证老格式、读取得到模糊结果，持久 `UNKNOWN`，阻止旧签名等待再次触发 CRM，任务展示“该命令结果待核对”，保留活动已写收据。`CLAIMED` 有租约超时／定期扫描：仅查询目标回执或确定回滚证明，超过阈值转 `UNKNOWN` 并告警；恢复 worker 不自动重发。对账成功通过任务版本 CAS 一次性追加真实收据、退役旧等待；两个 worker 竞争只允许一个完成。失败/拒绝后后续事项由**新的持久 turn**继续，遇未知状态不可把整个任务伪装为全部完成；其他独立事务原子仍保留。

## 5. 优化五：前端任务导航、输入隔离与断流真相

### 5.1 现状与精确边界

已有能力不能重复当新功能：前端已 `getTurn`／`getTask` 补读、按原 `client_request_id` 重试，并按行解析最近任务，单个坏历史任务**只跳过该行**（`CRM-Client/src/components/sales-assistant/SalesAssistantChat.vue:365-567`；`src/schemas/assistant-contracts/index.ts:102-112`）；服务端会在接收后持久 turn，再发 SSE，并按本人／团队检查任务和 turn（`CRM-Server/app/api/assistant.py:150-189,310-390`）。需要修的是下列**代码路径可判定的边界**：

- 提案把 dict 放在 `waiting.confirmation_payload`（`assistant/proposals.py:83-98`），前端却用只含活动确认字段的 `ConfirmationPayloadSchema` 解析全部等待（`assistant-contracts/index.ts:26-51`）。当前提案 GET／SSE 解析不兼容；列表仍逐项跳过坏行，不是整表解析失败。
- `openTask` 异步请求失败静默保留旧视图；`resetTask` 不清 `submitting`，跨任务局部 `explicitNone` 不应携带到新任务／新等待（`SalesAssistantChat.vue:75-87,119-230,604-609`）。当前确认的进度预设还把 `quality_gate` 放进确认时展示（`:293-298`），与确认零模型调用不符。
- SSE terminal `onError` 只附文字，不补权威投影；网络 409 的 `detail.task` 未按类型解析（`SalesAssistantChat.vue:425-430,553-560`；`src/api/assistant.ts:98-119`）。普通成功拒绝文案“已拒绝这条 CRM 提议。”会命中 `includes('拒绝')`，渲染失败卡“写入未完成”；回执徽标还依赖 `startsWith('已记录')`（`assistant/proposals.py:225-235`；`SalesAssistantChat.vue:614-647`；`FailureCard.vue:17-30`）。
- 活动确认后可创建内部 `next_turn_id` 继续候选（`assistant/turns.py:371-417`）；SSE waiting 消费不保留它，GET 任务投影也不公开可补读的 active turn ID，刷新期间可能出现 `ACTIVE/waiting=null` 却不能开始新输入（`src/api/assistant.ts:138-146`；`app/api/assistant.py:108-123`）。现有 turn 恢复 worker 必须继续保留（`assistant/turns.py:457-469`）。

### 5.2 服务端协议与页面状态

把 `waiting.confirmation_payload` 改为**判别联合**而非松散可互换字典：`{kind:'activity_write', activity: FrozenActivityPreview}`、`{kind:'proposal', proposal_kind, candidate_id, evidence, target, phase:'offer'|'form', form_draft?}`；`waiting.field` 必须与判别值一致；服务端用 Pydantic 校验，前端用 Zod 对同一版本协议校验。**已完成**历史活动 payload／旧拒绝 receipt 仅读时兼容、只读回放；切换时**尚在等待**的旧活动确认不可仅标只读：先排空正在处理的 turn，再在任务 CAS 下保留冻结活动命令与最终评分、迁移展示 payload、签发新 `action_id/expected_version`，旧卡变 409；零模型调用、无第二条活动。未 claim 的旧提案等待退役旧动作，可在新规则下重新核证并签发新候选；已 claim／不明的旧提案**不可重发**，按历史待对账处理，保留活动收据。仍未知历史任务只隔离该行并显示解析告警，不吞掉整个最近列表。Pydantic/Zod 入参出参均明确 typed，不加 `any` 或随意 `dict` 业务边界（`CONTRIBUTING.md:13-84`）。

服务端投影补充可恢复的 `processing_turn_id/status`（或等价权威指针）、当前命令 `outcome_code`／是否可输入和**已提交收据**；仅 owner 可 GET 这些信息。`accepted`、`waiting`、`error` SSE 都有 `turn_id`／序号和结构化 `outcome`，文案只供显示。客户端消费 `next_turn_id`，或刷新时按投影查询这**同一**内部 turn，绝不为填补空白重 POST。首个创建响应丢失沿用原创建键重调 create 取得**原 task ID**，并以原 submit 键读取或幂等重试其首个 turn；已被接收且运行中的 turn 只轮询 `getTurn`；已知 task ID 却没拿到 submit 接受回执时，先 `getTask`，再用**原 submit 键**安全重试。409 解析 `detail={code,message,task}` 并替换当前匹配任务的投影、让过期卡只读，不自动替用户确认。

导航采用 `(task_public_id,navigation_epoch,waiting.action_id,expected_version)` 栅栏：A→B 后 A 的 GET／SSE／finally 不得修改 B 的页面、`submitting`、输入、等待或 pending 请求；切换/新任务同时清本地文本、`EXPLICITLY_NONE`、表单草稿和旧等待标记。GET 失败显示“未打开目标任务／可重试”，保留原任务且不误称新任务已打开。`EXPLICITLY_NONE` 仅对同一任务同一 `FIELD:next_action` 等待有意义，必须带原因／复查条件；一般输入不继承此 choice。历史动作卡只读；当前一张可交互卡由最新服务端签名等待决定。活动已提交而取消可选续办时，侧栏与收据必须继续显示活动已写入，不能笼统称“本次记录未保存”。

收到终结 `error`、未到终结帧、断线／超时：先按已知 turn ID `getTurn`，必要时 `getTask`，区别技术失败／业务拒绝／待核对及可重试状态。只把 turn 的错误码映射为错误卡；拒绝提案、静默跳过、活动成功用**类型化 action/outcome 与 `committed` 收据**渲染。`FailureCard` 不通过中文“拒绝”等子串判断；确认时显示“写入”，不展示虚构评分阶段。页面最终渲染须在真实 `/assistant` 交互验收，不用静态检查替代。

## 6. 优化六：原文承接、明确更正和下一步行动门禁

**现状（代码路径可判定）：** `TaskDraft.source_segments` 留用户原话；`intake_flow.py:55-151` 的列表合并可把 `(owner,action,due_date)` 改日期后的两条动作同时保留。`confirmation.py:47-95` 冻结的 `source_content` 拼接全部原文；`proposals.py:39-62` 又从持久行动项派生后续任务；`crm_proposal_commands.py:139-174` 只用原文包含引用／ISO 日期判断可执行。故“不是周三，是周五”中的旧周三仍留在原文是审计需要，**不能**因此再次取得下游命令资格。`coordinator.py:317-348,203-244` 在明确客户更正后仍可能先取旧 `authority.customer_public_id`；其他补充则应继续复用原客户绑定。上述是代码路径推论，不声称已观测实际产生旧日期任务。

**三层结构和优先级：**

1. **不可变证据层：**首句 `goal`、按序只追加的用户 `source_segments`，每段存 `segment_id/turn_id/recorded_at/timezone/原话`；不加入系统问题、模型摘要或评分。若更正，旧语句保留并以显式 `superseded_by` 关系标注旧有效项，不删除审计证据。证据段的存在只证明“说过”，不证明“现在仍有效”。
2. **可修改 canonical 层：**为客户、活动类型、正文陈述、下一步、会议每条行动建立稳定事实／行动 ID、来源段、修订及 `ACTIVE/SUPERSEDED/EXPLICITLY_NONE`。明确更正目标时旧有效值失效；只补充内容时合并受影响字段，未受影响的 `ACCEPTED` 值和已确认客户绑定保持。若**明确**改客户则清旧权威 ID、重解团队／可见候选并重验权限；未找到不自动创建。行动由稳定 ID 更新负责人／日期／动作，不以完整三元组变化当成新增第二条；任何旧提案若来源事实被 supersede，撤销其当前等待与执行资格（已成功原子不回滚）。
3. **冻结／可执行层：**最终确认预览基于最新 ACTIVE canonical 稿、全部真实原文（注明更正）和唯一最终质量评分；整稿实质改变使旧评分／确认指纹作废，并以最终稿重评分。低于 60 只追问关键缺口；评分合格后独立检查下一步：明确动作而无时间可保存但不能瞎补；模糊如“继续跟进”须追问；明确暂无须用户给原因／复查条件并标 `EXPLICITLY_NONE`，不得派生空任务。确认只执行冻结命令，**零模型调用、零重评**；已提交活动不修改，后续更正需要新的独立业务流程，而不是覆写该活动（ADR §7；`CONTEXT.md:15-25,30-44`）。

后续建议只能遍历 canonical `ACTIVE` 事实／行动，并逐项复核引用源段确属该有效项；不能只对 `source_content` 做 substring。旧段可在审计和确认详情展示“原句→更正句”，不能当创建旧任务、旧阶段、旧客户绑定的授权。业务事实若来源撤销且尚未执行，记 `SKIPPED`／重新签发；提交未知保持待对账，不靠改稿删除未知命令。不得以优化更正为名重新让旧 Web Agent 或表单采用 2.0 局部合并规则。

## 7. 优化七：运维最小权限和自然语言日期证据

### 7.1 未决命令的授权、查询与裁决

**现状（代码路径可判定）：** `GET /v1/assistant/unknown-commands` 在读取当前用户后 `del current_user`，按 team 返回所有 `UNKNOWN`（`api/assistant.py:295-306`）；`CLAIMED` 滞留未纳入（`assistant/proposals.py:255-279`）。现有任务／turn GET 则仅 owner（`api/assistant.py:125-129,310-325`）。把“能看自己任务”视为“能读同组其他销售的未决命令”是越权，不应靠前端隐藏。

拆出**本人命令查询**与**明确授予的团队运维查询**：默认 owner 仅查本人所在团队的 `CLAIMED/UNKNOWN`；有独立 `assistant:commands:reconcile:team` 权限的操作员可看同团队分页、状态／时间筛选列表，权限在服务端校验，团队由登录上下文取得，客户端不能指定任意团队。列表字段仅命令引用、类型、状态、task／action 引用、创建／上次核对时间与非敏感错误码；姓名、原文、表单金额、客户全文需沿有权任务／CRM 资源的二次授权读取，不直接随列表泄漏。人工裁决单独鉴权，提交目标关联回执／回滚证明、operator ID、理由、证据时间与审计事件；有确切提交证明才可标 `SUCCEEDED`，确知未提交才可 `REJECTED`，模糊情况下保留 `UNKNOWN`，不得从运维页面点击“重试创建”。旧无归因 claim 标明来源不明并保持审计。访问／裁决日志不得记录不必要的原文；跨团队必拒绝。权限名及迁移要经产品／安全审阅，不以设计文档宣称已配置角色。

监控：按 team 和命令类型统计 `CLAIMED` 超租约、`UNKNOWN` 年龄、目标关联缺失、人工裁决数、重复指纹冲突；按来源策略统计旧发表拒绝／证据 `UNAVAILABLE`／回填差异；前端统计任务 schema 单行解析失败、断流补读、409 与内部 turn 停滞。业务客户原话、金额不入指标标签。异常率超过发布阈值时关**新提案／新发表**的功能开关而不删除活动和回执，不允许回退到不安全的团队全量查询或猜测对账。

### 7.2 相对日期必须可追溯、不靠 ISO 原文包含

**现状（代码路径可判定的拒绝条件，非实测故障）：** `resolve_follow_up_time(text, base=...)` 支持有限绝对／相对日期（`app/utils/time.py:52-79`），但后续 `follow_up_task_create` 校验要求解析后的 `due_date` 是原文中逐字出现的 ISO 时间且与动作同分句（`assistant/crm_proposal_commands.py:139-174`）。用户说“我下周三发方案”时自然语言可以指向日期，但未必含 ISO；不应在无歧义证据时误报创建成功，也不应模型自行编出 ISO。现有承诺／任务字段已有 `due_at_text/due_at_granularity/due_at_timezone/evidence_json`（`app/models/sales_commitment.py:167-180,245-249`）。

为**每条** canonical 行动存：`action_id`、原句 segment ID、原话范围／准确引用、`due_at_text`、接受该句时固定 `anchor_at`、`Asia/Shanghai`、解析器版本、粒度 `DATE|DATETIME|UNKNOWN`、解析状态 `RESOLVED|AMBIGUOUS|UNRESOLVED|EXPLICITLY_NONE`、派生 `due_at`（若有）、用户更正关系。只解析被该 action 引用的原话；如“下周三”使用确定的当时基准和业务时区，不在重试／午夜过后用新 `now()` 改写；有时刻保存到时刻，只有日期时页面显示日期粒度，执行层按已审定的本地到期时刻政策（与现有纯日期 23:59:59 行为对齐）转换，不能把跟进时间解析器的默认 09:00 偷用于任务。若基准／范围／表述存在歧义、缺负责人或目标，不创建任务，只针对该字段追问或保留无到期建议；给出确定日期后以**原话＋基准＋解析证据＋最终 canonical 值**联合验证，不要求原话逐字含规范化 ISO。用户改“周三→周五”时旧解析虽保留审计但不得生成旧待办。绝不把 `EXPLICITLY_NONE` 时间偷换成当天或创建没有可证明到期时间的任务。

## 8. 跨七项的状态、接口与事务规格

以下均是**拟新增／拟调整协议**，不是今天已上线 API。

| 边界 | 必需字段／行为 | 拒绝、幂等、权限 |
| --- | --- | --- |
| `GET /v1/assistant/tasks/{id}` 与同任务 turn GET | 保留 `version/waiting/committed`；增 `processing_turn_id/status`、当前命令类型化状态和结果码；字段对历史无命令任务可空。 | 本人＋团队；正在处理 ≠ 可再提交；读历史只读。 |
| `POST /v1/assistant/tasks/{id}/submit` | 现有 text／submit_field／confirm／cancel 继续；为表单加判别输入 `submit_opportunity_form`，含 `candidate_id`、完整字段、`client_request_id/action_id/expected_version`。 | 先请求 ID／指纹去重，再核对签发动作和 task CAS；409 含最新同 owner task；不同键旧卡不能执行。 |
| `waiting.confirmation_payload` | 判别 `activity_write`、`proposal`，proposal 的 `offer` 与 `form` 子状态；提案仅供服务端签发的候选和用户表单草稿；当前历史只读适配。 | 前后端封闭 schema；不能把活动 payload 当提案解析；未知版本显示安全降级，不作可执行卡。 |
| CRM 目标效果 | `(team_id,command_id,effect_kind)` 唯一，存指纹、目标 ID／快照 ID、提交时间／状态；助手 `CLAIMED` 只表示已申领。 | 与对应目标实体提交同事务；相同指纹重放查回执，不同指纹拒绝；成功只在相关回执存在时。 |
| 本人／团队运维查询与裁决 | `CLAIMED/UNKNOWN` 状态、分页、最小字段、审计。 | 本人仅本人；团队查询／裁决独立权限；不允许从历史 claim 推断成功。 |
| 旧客户档案发表与证据读取 | `policy_version/eligible_revision/source_snapshot_hash` 与已核验来源链；独立调度事件 metadata。 | 客户级发表栅栏与读时 `UNAVAILABLE`；源不明失败关闭、不修改 2.0 原始事实。 |

确认活动继续使用既有冻结命令和同库活动写入事务；后续商机创建、后续阶段推进、后续任务和事实**每笔独立**。活动提交后若内部提案 turn 失败，活动回执仍持久；SSE 断开不取消已接受 turn；任务的交互投影和 CRM 目标效果以各自持久结果为准。**新命令**只有目标事务内相关回执可把跨事务未知收敛为成功；老命令没有回执时须经授权人工核验一对一目标提交证据，不能由任务状态或相似对象推出成功。模型不能签发 `action_id`、`command_id`、证明 target 归因或决定 `UNKNOWN→SUCCEEDED`。

## 9. 逐项可执行验收矩阵与本轮证据

下表是验收合同；后面的证据表逐行区分隔离 MySQL 服务级（M）、FastAPI TestClient（A）、mock API 前端组件（V）、独立 HTTP（H）和真实浏览器（B）。测试构造的候选／模型输出及浏览器故障注入不是真实模型提案；一个层级的结果不能冒充另一层。证据仅覆盖实际触及的输入、事务和身份；未触及的条件明确列为缺口。隔离库只用 `127.0.0.1:3308/crm_assistant_acceptance`，未清理历史记录，未运行会取消全部 ACTIVE 任务的 `assistant-design-scenarios.spec.ts`。以下“局部通过”不是对应发布门禁批准。

| ID | 输入／故障注入 | 必须观察到的结果 |
| --- | --- | --- |
| S01 来源 | 同客户已**恰一**活跃旅程；只加 2.0 活动并实际走 `record_event` | 2.0 活动和 `activity_added` 都写入；旧展示／合格事件／合格进度及新发表正文不因该事件改变；共享聚合时间不能伪装旧水位。 |
| S02 来源 | 同一旅程先有旧事件 t1，再加 2.0 事件 t2 | 混合旅程仍在旧档案；其旧视图事件、显示日期与排序反映 t1 及其他合格来源而非 t2。 |
| S03 来源 | 旧活动＋任务与 2.0 活动＋任务各一条，分别硬删除并留 tombstone、FK `SET NULL` | 旧来源按 tombstone 保有可核历史；2.0 派生任务／承诺／事实／向量均不能借 NULL 外键入旧视图；独立来源的 NULL-FK 任务仍可按明确证据纳入。 |
| S04 来源 | 经 `deal_journey_event` 或 `business_flow` 间接指回 2.0 的事实与存量 citation | 旧候选／partial 继承不能发表该链；已存引用 `/profile/evidence` 为 `UNAVAILABLE` 且无摘要和链接；2.0 活动自身仍可按权限查看。 |
| S05 水位 | >50 活动／事实／旅程，>200 事件、>100 任务／承诺；最大合格 ID 位于展示窗外 | 展示仍遵守窗口，完整合格进度能看见窗口外变化；跨 >200 个客户翻页的对账覆盖每一客户而非停在第一页。 |
| S06 删除 | 发表后删除最高合格活动 N，留下合格 tombstone M | 删除进度上升且旧正文最终删除该活动；存活活动最大 ID 可下降，不死锁、不把新删事实重新显示；等价扫描无重复发布。 |
| S07 竞争 | A 读旧草稿，B 在 A 发表前写入合法活动／删除，分别测普通事件与全量对账 | A 不能切当前指针／设 READY，原合格版本仍可读；B 进度触发新轮；新轮发表合格最新视图。MySQL 双会话而非只做顺序 SQLite。 |
| S08 隔离竞争 | 同 S07 但 B 仅写 2.0 活动并改混合旅程聚合 | 旧合格进度不前进，A 所发表内容亦不携带 2.0 贡献；2.0 活动／事件仍保留。 |
| S09 发表分支 | 草稿 partial 继承旧引用、内容哈希命中去重；期间来源资格撤销 | 全量、partial、duplicate 三分支都核来源／策略／指针；来源不明只阻该客户，不把旧错误 citation 标为 READY。 |
| O01 候选 | 已确认活动仅写“客户考虑采购”，不含金额人数日期；CRM 无可匹配商机 | 出一条有原话证据的 `opportunity_create` 提议；尚无创建，接受后展示 Agent 内表单而非旧弹窗。 |
| O02 静默去重 | 同客户已存在高置信匹配商机；另造同名但目标不明 | 前者不展示新建并不创建重复项；后者不能仅凭名字自动创建／误绑定，按歧义安全处置。 |
| O03 表单 | 逐次缺模块、金额≤0、人数≤0、非法日期、订阅无年限、跨团队产品 | 对应字段错误，可更正，不 claim／不写商机；保存有效后仅生成一条冻结命令；表单补值无须逐字存在旧活动。 |
| O04 幂等 | 同 `client_request_id`＋同表单两次；同键改金额；旧 `action_id`；另一用户/团队 | 同输入一 turn／一命令／一商机；改载荷和旧动作 409 附最新可读任务；跨身份无信息泄漏、零写。 |
| O05 名称 | 表单商机名留空，服务端自动命名；模拟提交后丢响应 | target 相关回执精确指向一次创建的 public ID；不能用 `name = None` 查询或同名记录当证明；活动保持已提交。 |
| O06 阶段 | 确认前目标商机阶段／版本已变 | `SKIPPED`、无第二次推进、无旧确认重用、无错误覆盖；其他原子仍独立。 |
| O07 分离 | 活动创建成功、商机创建拒绝、另一阶段提案失败 | 活动唯一和收据不回滚；创建／阶段各有独立命令和不同拒绝／错误状态，不合并事务。 |
| C01 归因 | claim 后第三方创建同名商机，再让助手丢响应 | 无 target 关联回执时不能报本命令成功；保留 `UNKNOWN`／人工待核，不自动再创。 |
| C02 归因 | claim 后第三方推进目标阶段；本命令尚未调用或结果丢失 | 阶段已变化不能算助手执行成功；可证明提议过期则静默 `SKIPPED`，无法证明本命令效果则 `UNKNOWN`。 |
| C03 归因 | 目标创建／阶段提交成功，助手在写回执前崩溃并恢复 | 只读按 `(team,command_id,effect_kind)` 关联准确效果；补一次助手成功收据；绝不第二次目标写。 |
| C04 并发 | MySQL 两 worker 同时取同一命令／同一商机旧阶段快照 | 一个目标效果及收据；另一方只得到原结果或确定过期，无无条件覆盖；不同参数同命令 ID 冲突。 |
| C05 多提交 | 推进到 100% 阶段成功，第二次自动赢单提交前／后分别故障 | 阶段效果确实成功；赢单各自显示未证实或成功，不说“全部原子成功”，不重做阶段。 |
| C06 老数据 | 旧 `CLAIMED/UNKNOWN` 无目标相关 ID，现场存在同名商机 | 不能自动升级成功；最小运维列表标历史无归因，保留审计和无重放保护。 |
| R01 确拒 | 源 revision 变化、撤销权限、无审批流或确认前 invalid 表单 | 确定无目标效果时为 `REJECTED`／仍可修复的表单新 wait，旧 action 退役；已写活动存在，旧确认重放无第二次 create。 |
| R02 未知 | 目标提交边界之后丢响应、停电或数据库暂不可达 | `CLAIMED→UNKNOWN`，前端只显示待核对、不能再点击旧确认；后台只读相关效果，未证实不自动重发。 |
| R03 滞留 | worker 被杀于持久 `CLAIMED` 后、目标调用前／后各一次 | 租约扫描列出 `CLAIMED` 并核真实效果；有确切无调用证据可拒绝，无法证明转 `UNKNOWN`，不让记录永久隐身。 |
| R04 争抢 | 两个核对 worker 同时发现同一目标回执 | CAS 后最多一条成功收据／一个退役等待；可重复查询不二次发布下一张卡。 |
| U01 协议 | 构造真实提案 wait（含 payload），任务 GET／turn GET／waiting SSE 各走一遍；再迁移一条存量未确认活动 wait | 同一判别联合在前后端解析；当前提案可操作；最近任务的另一坏历史项只被单行隔离；旧冻结活动命令和评分保留，新签名卡仍可确认一次，旧卡失效。 |
| U02 导航 | 打开 A 后立刻点 B、令 A GET 或 SSE 最后完成；再让 B GET 失败 | B 不被 A 回包／finally 覆写；失败明确保留 A 或当前视图且显示未打开 B，旧等待不获得交互权限。 |
| U03 输入 | A 的 `EXPLICITLY_NONE` 已选择，切到 B 的 FIELD／普通文本；再回 A | B 不继承 choice／文本／表单；只有同任务同 next_action wait 能提交有理由的 `EXPLICITLY_NONE`。 |
| U04 SSE | 接受后断流、只收到终结 error、收到 409 最新 task，分别刷新 | 前两者 GET 原 turn／task 得实际处理／拒绝／未知，409 淘汰旧卡；不把已接受请求重新 POST，也不凭错误文案称活动未写。 |
| U05 内部 turn | 活动已成功并签发 `next_turn_id`，在提案出现前刷新 | 任务投影可发现同一内部 turn，轮询直到 waiting／完成；无需另起 turn，不遇无意义 409 或无限 ACTIVE 空等待。 |
| U06 文案 | 成功拒绝提案返回“已拒绝…”；活动已写后取消后续提案 | 显示正常拒绝和活动已写，不渲染“写入未完成”；回执徽标只取 typed committed，不查汉字子串。 |
| D01 更正 | 原文“周三我发方案”，后补“不是周三，是周五” | 两句原文可审计；同一 canonical action 日期只有周五有效，原旧周三提案失效，不因 source_content 含周三再建任务。 |
| D02 更正 | 会议行动的负责人、动作与日期分别更正；客户已绑定后明确换客户 | 行动 ID 不变或由明确替换关系接续，不把旧／新行动并集成两笔；明确换客户清旧绑定并按权限重解，普通补字段不重搜客户。 |
| D03 评分 | 低分稿补足正文、缺/模糊下一步、明示暂无及原因；最后确认 | 只记录最终 `>=60` 评分；下一步缺口单独追问；确认零模型调用；冻结载荷与最终稿、有效更正一致。 |
| D04 旧卡 | 更正正文／客户后提交旧 `action_id` 与旧评分卡 | 409 最新任务，零 CRM 写；新增合法确认重新冻结且仅一次活动，提交后不准改活动类型或原文。 |
| T01 日期 | 固定 `anchor_at` 的“我下周三发方案”，跨夜重试 | 原句／行动／基准／时区／粒度／解析版本同一，按已审政策得到稳定日期；原句无需含 ISO；只对有效行动产生至多一条任务。 |
| T02 歧义 | “月底左右”“有空发方案”，或日期无可证明行动归属 | `AMBIGUOUS/UNRESOLVED` 追问或不建任务；无臆造 ISO、无“已创建”假回执。 |
| T03 权限 | 普通成员查同团队他人的未决命令；已授权运维跨团队／分页查询并裁决 | 前者只能查本人，跨团队拒绝；运维仅本团队最小字段且审计；模糊证据不得判成功、不得自动重发。 |
| T04 回滚 | 新商机提议／旧档案发表开关关闭，已有活动、历史不明 claim 仍在 | 无新增不安全写／发表；活动／准确 CRM 收据与 owner 查询保持可用；旧读时来源门禁继续有效。 |

### 9.1 S01–S09：来源、进度与发表（隔离 MySQL）

| ID | 实际输入、边界与观察 | 尚未覆盖／结论 |
| --- | --- | --- |
| S01 | M：`test_s01_assistant_activity_real_writer_commits_event_without_legacy_publication_change`，恰一活跃旅程先发旧档案，再由实际活动 CRUD 写 `ASSISTANT_2`／`activity_added`；共享旅程时间到 t2，但合格 revision、旧内容／水位不变，重发只去重一次、正文不含私有活动。 | 隔离样本验证；生产存量正文和真实 Web 未查；**局部通过**。 |
| S02 | M：`test_s02_mixed_journey_uses_only_eligible_event_time_and_order`，同旅程旧事件 t1、2.0 事件 t2 均落库；旧视图只含 t1、旅程仍在且旧显示时间 t1，发表正文不含 t2。 | 样本旅程验证，非全量历史聚合字段盘点；**局部通过**。 |
| S03 | M：`test_s03_deleted_origins_keep_legacy_task_and_exclude_assistant_task_after_set_null`，旧／2.0 活动各带任务、承诺和事实，删活动留 tombstone、FK 置 NULL；旧任务和独立来源 NULL-FK 任务仍在视图，2.0 任务／承诺／事实排除，删除 revision 上升，发表正文遵守过滤。 | 向量所有来源及生产历史 NULL-FK 组合未逐条验证；**局部通过**。 |
| S04 | M＋A：`test_s04_indirect_private_fact_is_stored_but_citation_resolves_unavailable` 经 `business_flow` 间接指向私有活动；事实仍在表但旧上下文／正文没有。`test_s04_certified_historical_fact_citation_becomes_unavailable_over_profile_api` 先发已认证引用，再把来源改指 2.0 事件；partial 发稿拒绝、指针不动；MySQL fixture 上的 FastAPI **TestClient** 返回无权限 403，获权 200 且 citation 为 `UNAVAILABLE`、`snippet/link=null`。 | 非独立 HTTP；生产存量污染正文和业务授权的 2.0 页面未验；**局部通过**。 |
| S05 | M：`test_s05_display_window_does_not_hide_highest_eligible_id_outside_it` 构造 51+1 活动，窗口仅 50、隐藏最大 ID 仍入水位，其内容变化推进 revision/hash；`test_s05_all_display_windows_preserve_complete_eligible_source_watermark` 构造 >50 事实／旅程、>200 事件、>100 任务／承诺，隐藏各类最大 ID 仍在来源水位；`test_s05_reconciliation_paginates_more_than_two_hundred_team_customers` 以 dry-run、limit=200 扫齐 206 客户。 | 合成数据页，不是生产全库对账；**局部通过**。 |
| S06 | M：`test_s06_deleting_highest_eligible_activity_advances_deletion_and_deduplicates_replay`，发含最高活动 N 的版本后删除 N，存活最大 ID 下降但删除 revision 上升，第二版本去除 N、重复发稿仍只有两版本。 | 未据此证明生产中所有删源可恢复；**局部通过**。 |
| S07 | M：`test_s07_rr_stale_publication_rejected_then_fresh_publication_succeeds` 和 `test_s07_full_reconciliation_competes_with_stale_publication` 分别在 MySQL `REPEATABLE-READ` 两会话下对合法写入／删除各执行；B 提交后 A 的旧草稿 `PROFILE_PUBLISH_REJECTED_STALE`，原认证版本指针不动，对账分支先 `STALE` 且排一轮，随后新版本仅含最新合格视图。 | 定向交错非生产流量；**局部通过**。 |
| S08 | M：`test_s08_rr_private_writer_does_not_poison_stale_eligible_draft`，MySQL RR 两会话：B 写私有活动／旅程事件且共享聚合到 t2，A 旧合格稿照常发表；合格水位不变、正文不含私有贡献，私有数据仍在。`test_deal_journey_source_fence_mysql.py` 另覆同客户旅程旧快照并发栅栏。 | 只证明所造交错；**局部通过**。 |
| S09 | M：`test_s09_full_partial_and_duplicate_publishing_recheck_provenance_and_pointer`，旧引用源删除后 partial 拒绝并保原指针，新 full 去除内容；`test_s09_unknown_source_blocks_every_publication_branch_without_moving_pointer` 与 `test_s09_committed_opportunity_deletion_revokes_draft_provenance_for_every_branch` 分别对 full／partial／duplicate 三分支注入不明事件、删除商机来源，均拒绝且只影响当前客户指针。 | 三分支隔离数据验证；真实存量引用的批量隔离／重建及差异审计未执行；**局部通过，不满足 A 门禁**。 |

只读存量审计（2026-10-03）：新增一次性离线入口 `CRM-Server/scripts/audit_legacy_profile_versions.py`，逐版本核对 team/customer 归属、签名、六段历史正文与**当前** 2.0 原文的直接命中，以及逐条 citation 的当前可用性；所有非空历史正文标为 `body_unproven_versions`，因为签名和当前来源匹配都无法重建发表当时的全部来源。输出只含固定聚合计数，MySQL 使用只读一致快照；异常仅输出固定 `audit_error`，不输出正文／标识／数据库错误。SQLite 定向测试用 `--no-cov` 退出 0（`2 passed, 1 warning`），包含直接污染、不可用引用、跨团队拒绝、无写 SQL／无业务内容输出；指定 `127.0.0.1:3308/crm_assistant_acceptance` 隔离 MySQL CLI 退出 0，实际聚合：版本 0、current 指针记录 16、无效 current 指针 0、不可用引用 0、正文无法证明来源的版本 0。**零版本是空样本，不是历史正文安全结论**；当前 2.0 原文的字面包含只能发现一类污染，改写／转述／已删除来源不可由此证明清白；没有生产或待发布副本、旧／新正文影子差异、按团队迁移水位及全量隔离／重建记录。此探针不提高 S01–S09 或 A 门禁结论。

**2026-10-05 A 门禁只读续查（指定隔离库，非生产存量审计）：**`venv/bin/alembic current` 报 `151_assistant_proposal_policy (head)`；`venv/bin/python -m scripts.audit_legacy_profile_versions` 使用 MySQL `REPEATABLE READ` 只读一致快照，退出 0，固定聚合为 `versions=0`、`current_pointers=17`、`invalid_current_pointers=0`、`body_unproven_versions=0`、`unavailable_citations=0`。另在同一指定隔离库以只读一致快照查询、不输出客户 ID／正文：current 非空版本指针 0；来源进度 3 行、跨 2 团队，全部 `LEGACY_PROFILE_ELIGIBLE_V1/UNVERIFIED`，eligible revision 合计 16、deletion revision 合计 0。审计器定向测试本次 `2 passed, 1 warning`，涵盖直接复制私有文本、不可用引用、跨团队归属和无写 SQL。current 计数从上次 16 到本次 17，只能说明隔离库当前快照不同；版本仍为零，故**没有历史正文可验证来源、不可凭零异常提高 A 门禁结论**。尚须取得获准的生产或待发布历史副本，由 SELECT-only 账号运行相同盘点，并补齐当时来源重建／删源证据、按团队高水位、旧／新正文差异与隔离／重建记录；未取得该环境或这些证据时 A 继续未批准。

**2026-10-06 本地 Docker dev 存量只读盘点（用户授权；非待发布副本）：**按 `CRM-Server/.env` 定位 `crm-mysql-dev`／`localhost:3307/crm_db`，在单次 MySQL `REPEATABLE READ`、`START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY` 快照中完成以下统计，最后 `ROLLBACK`；未使用网页登录密码、未写 dev 数据，输出仅含聚合值。dev 的 `alembic_version` 为 `149_assistant_command_reconciliation_permission`，尚无迁移 150 的 `source_attestation_json`／`source_discriminator` 两列，所以**不能运行**新版 `scripts.audit_legacy_profile_versions`；本次使用与旧 schema 兼容的临时只读查询，引用可用性调用现有 `CustomerProfileEvidenceResolver`，在同一快照内按团队、客户和完整引用缓存解析。dev 配置中的数据库身份是 root，**不是 SELECT-only**，故本次不能替代生产／待发布副本的最小权限审计。

同一快照内：历史档案版本 2,439（SUPERSEDED 2,353、PUBLISHED 85、PUBLISHED_WITH_WARNINGS 1），跨 3 团队；版本归属异常 0。六段正文的历史来源均未证实（2,439 版本）；与当前 2.0 活动原文（长度至少 16）的直接包含命中 0，不能证明不存在转述／已删除来源污染。引用总数 109,046：当前规则下可用 86,759、不可用 22,287；2,325 个版本含不可用引用。不可用引用按类别：`customer_fact` 20,938、`follow_up_task` 1,349；这表示现行解析器无法确认来源，**不等于逐条证明已删除或遭 2.0 污染**。current 记录 87、非空版本指针 86、无效指针 0。旧来源进度 87 行、跨 3 团队，均为 `LEGACY_PROFILE_ELIGIBLE_V1/UNVERIFIED`，eligible revision 合计 470、deletion revision 合计 0；匿名团队行数／eligible revision 范围分别为 1／0–0、25／0–83、61／0–1。另一只读快照仅核对 current：86 个被指向版本中 43 个含目前不可用引用（总 current 引用 2,227，其中不可用 297）；**此项不可与前述快照视为原子观察**。旧 schema 无来源认证列，不能声称历史签名已核验；dev 结果表明存量风险规模，但不是 A 门禁通过。仍缺待发布同版本制品、SELECT-only 副本、历史来源重建、旧／新正文差异及不可用引用的隔离／重建证据；A–D 继续未批准发布或扩大流量。



### 9.2 O01–O07：候选、页内表单和独立授权

以下 O 行主要来自隔离 MySQL 的 `test_assistant_opportunity_scenarios_mysql.py`；候选由固定 quote、测试设置 `authority_json.proposal_candidates` 或 `_candidate_hints()` 规则产生，**不构成真实 LLM 产出**。

| ID | 实际输入、边界与观察 | 尚未覆盖／结论 |
| --- | --- | --- |
| O01 | M：`test_o01_quote_without_commercial_values_offers_form_without_creating`，已持久活动只有“客户考虑采购”，无金额人数日期；服务签 offer 并引用原句，确认后为新签名 form wait，活动已 committed，商机／claim 数均 0。V：`SalesAssistantProposal.spec.ts` offer→内嵌 `OpportunityProposalForm`→带新 action/version 的结构化提交，不调用旧直接创建 API。B（2026-10-03）：另建受限隔离团队，5191 Chromium 指向 8020 API，直接打开固定来源活动签发的 offer，点击“确认”后实际进入页内 form wait；填完后对同一任务 `/api/v1/.../submit` POST 200，DOM 显示“CRM 命令已按目标系统实际结果核对完成”“已完成”“活动已写入”“商机已创建”。 | 该活动和候选由隔离 fixture／规则产生，浏览器观察 offer→form→回执，但不是模型从对话签发；未观察真实模型更正和评分；DOM 文本不是截图；**局部通过**。 |
| O02 | M：`test_o02_existing_active_deal_suppresses_unqualified_create_offer` 同客户已有匹配活跃商机时不签新建卡；新增 `test_o02_ambiguous_named_target_with_multiple_active_deals_has_no_create_offer` 在同客户“一期系统／二期系统”与“客户考虑采购系统”并存时先观察旧规则误签，收紧为部分名称重叠时不签卡，保留两商机、活动且 claim 0；单元 `test_purchase_candidate_with_named_target_ignores_unrelated_active_deal` 保持无关商机不会拦住明确的不同采购目标。 | 部分名称保护是保守兜底，未批准的高置信匹配阈值／目标不唯一业务决策仍待审；真实模型匹配、其他语义别名与消歧 UI 未验；**局部通过**。 |
| O03 | M：`test_o03_invalid_form_edits_reissue_wait_then_valid_form_freezes_one_command`，九组缺模块、非正金额／人数、非法日期、订阅年限及外团队产品输入，每次字段错误、新 action 且零 claim／商机；原文没有金额 `18000`，有效补值后仅一冻结、一 claim、一 target 商机回执。V：表单服务错误可更正、局部草稿保留。B（2026-10-03）：同一固定来源 offer→form 任务填有效值 POST 200；独立 task GET 为 `COMPLETED/SUCCEEDED`、活动及创建两条 committed 收据；独立 MySQL 核出该任务一条商机和唯一 `opportunity_create` 精确效果，`target_public_id=opp_cdd110fe1a8f44b3afb11746efbf0c19`、`command_id=acm_01513a48607d44b2a6d919a2c84d5c18`。另一个任务用独立 HTTP 提交人数 `0`，返回人数错误及新签名 version 3 form wait；浏览器持旧 version 2 表单提交得 409，改用服务端草稿及字段错误，修正人数为 `4` 后 POST 200。 | 只在浏览器实测人数错误及重签，不等于九种错误路径均被浏览器覆盖；同链效果是隔离 fixture 而非真实模型；**局部通过**。 |
| O04 | M：`test_o04_same_request_replays_turn_but_changed_payload_and_stale_action_conflict` 只接受请求未运行 turn，一 request／turn、零商机；`test_o04_http_form_replay_conflict_and_cross_identity_write_once` 从签名 form wait 经 FastAPI TestClient 提交有效表单，首次 SSE `accepted, waiting` 与 turn GET `SUCCEEDED` 一致；同键同载荷补读原 turn，改金额／旧 action 得 409；有效跨团队用户及同团队另一用户对 task、turn、submit 均 404、零写；最终一成功表单 turn／claim／商机／精确目标回执。H：独立隔离 Uvicorn 8020 与独立 HTTP 客户端重现 task GET 200、POST accepted／waiting SSE、turn GET 成功、同键重放、改金额及旧 action 409，独立会话核唯一 request／表单 turn／精确效果；另以有效跨团队及同团队非 owner 身份实际 GET task／turn、POST submit 均 404，身份各零 request／turn／task、外团队零效果。B：上述同一团队浏览器旧 action/version 对服务端重签卡 POST 409，显示新签名和服务端草稿；改合法值 POST 200。 | 浏览器未实走同键重放或跨身份 UI；H／B 提案均来自固定活动／fixture，不是真实模型；**局部通过**。 |
| O05 | M：`test_o05_auto_name_survives_lost_service_response_with_exact_target_effect`，商机名留空，真实目标服务内提交后模拟连接异常；另一会话读取精确 `(team,command,effect_kind)` 的目标 public ID／审批记录，一商机自动命名，claim `RECONCILED`，原活动仍是第一收据。 | 丢的是服务响应，不是真实进程断电／独立 HTTP；**局部通过**。 |
| O06 | M：`test_o06_stage_changed_after_offer_skips_without_a_command_claim`，第三方在 offer 后推进同一商机；旧版本确认记 `SKIPPED`，snapshot 只有两条、无本命令 claim，旧 action 再交冲突，活动保留。 | 真实交互卡／模型阶段建议未验；**局部通过**。 |
| O07 | M：`test_o07_refused_create_and_independent_stale_stage_preserve_activity` 先拒绝创建 `REFUSED`，后独立阶段提案被第三方推进变为 `SKIPPED`，无目标调用。新增 `test_o07_refused_create_then_independent_stage_target_failure_preserves_activity` 两种注入均走 `settle_proposal()` 与真实阶段目标执行器、持久 `STARTED` claim：提交前拦截目标外层 commit，确认唯一调用尝试、零精确效果／第二次推进，claim `UNKNOWN` 且旧签名重试不再执行；目标已提交而助手丢响应时，精确阶段回执只读核对为 `RECONCILED`，仅一新快照／目标效果／助手收据。两种场景均保留唯一活动及独立 `REFUSED` 创建回执，创建／阶段 proposal key 不同。 | 服务级 MySQL 故障注入，不是真实进程停电、独立 HTTP 或真实模型阶段提案；**局部通过**。 |
额外撤销边界（后端公开 `offer_next_proposal()` 路径）：`test_negative_purchase_intent_within_quote_does_not_offer` 的“客户不考虑采购分析平台”与 `test_later_target_withdrawal_in_same_clause_prevents_offer` 的“客户考虑采购分析平台。更正：暂不采购培训系统，也不采购分析平台”均先复现错误签卡，再在修正后无活跃提案；同文件仍验证取消其他目标不误杀本目标，以及再次确认相同采购语句可提议。规则只认有限中文否定模式；重复原句尚无独立发生位置／冻结证据 ID，不能据此认定一般语义撤销或真实模型链通过。
补充定向探针（2026-10-02，指定隔离 MySQL）：同客户既有活跃商机“分析平台”，新原话“客户考虑采购分析平台培训服务”，现行 `validate_candidate()` 保守名称包含拦截使 `offer_next_proposal()` 返回 `offer=False, completed=True`，商机仍为 1。这是**不同采购目标被误拦**的反例，不是自动创建或重复商机；未放宽去重阈值，需先审定 §10 的业务高置信阈值及歧义处置，O02 不得视为完整通过。O04 `case()` 初始化的定向故障注入分别在第三次 flush（部分 setup）、`db.commit()` 之前以及跨身份 setup 提交后抛异常；各探针原异常传播，按本次唯一 suffix 查询持久 user/team/role/product/permission 或外来 user/team 均为 0。此结果只覆盖注入位置及唯一标识记录，不等于所有跨身份写入或整个 O04；主 fixture 提交后异常的独立回归已在同隔离库随 O 文件执行，`12 passed, 61 warnings in 7.34s`。探针运行时后台智能刷新曾打印缺失 `crm_langgraph_checkpoints` 的栈迹，不据此断言整体运行环境健康。


### 9.3 C01–C06：目标事务归因

| ID | 实际输入、边界与观察 | 尚未覆盖／结论 |
| --- | --- | --- |
| C01 | M：`test_unrelated_same_name_creation_does_not_settle_claim`，claim 后第三方同名创建，无本命令效果；只读核对不认领，claim 转 `UNKNOWN`，活动保留、未第二次创建。 | 故障由测试设 claim／丢助手响应，不是真实端到端 HTTP；**局部通过**。 |
| C02 | M：`test_third_party_stage_change_is_not_assistant_effect`，第三方改阶段；目标版本检查报 stale，缺精确效果时 readback 空、已 claim 核对为 `UNKNOWN`（**不是**因阶段变化就报成功／跳过）；O06 提供目标**尚未调用**时的 `SKIPPED` 对照。 | 两种时序被分开验证，未跑生产并发流量；**局部通过**。 |
| C03 | M：`test_creation_target_commit_recovers_exact_receipt_and_replay` 验证创建服务内部提交目标、审批及效果、同指纹重放仍一次创建，不同指纹冲突；`test_r02_c03_postcommit_response_loss_recovers_exact_stage_receipt_without_replay` 在阶段**外层 commit** 后注入响应丢失，独立会话先见目标 snapshot＋精确效果，再一次补助手收据，未再写阶段。 | 独立目标提交和恢复已测，非完整 HTTP 提案到 CRM 的实际模型链；**局部通过**。 |
| C04 | M：`test_two_target_workers_same_command_commit_one_stage`、`test_two_target_workers_same_create_command_commit_one_opportunity` 并行 MySQL 会话争同 command，分别只落一 snapshot／一商机／一**目标效果**；`test_c04_two_target_workers_different_fingerprints_same_command_do_not_replay` 另一指纹获 stale 或指纹冲突，赢家版本精确加一。助手收据最多一条由 R04 的核对竞争测试另证，不能从这两个目标 worker 用例推出。 | 线程栅栏覆盖这些交错，非所有外部写入时序；**局部通过**。 |
| C05 | M：`test_win_second_commit_failure_preserves_only_stage_effect` 在第二次赢单 commit **前**故障，仅阶段精确效果已提交，读回 `auto_won=UNVERIFIED`；`test_auto_win_commits_distinct_stage_and_win_effects` 正常路径写阶段／赢单两条效果、目标版本各增一。`test_win_second_commit_response_loss_recovers_both_effects_without_replaying_stage` 在第二次外层 commit **后**丢响应，新会话读到两条精确效果，再只读核对一次补助手收据、无第二次阶段写入。提交间交错 `test_reconcile_between_stage_and_auto_win_commits_preserves_first_receipt` 在第一笔阶段 commit 后、第二笔赢单 commit 前扫描：唯一阶段收据 `auto_won=UNVERIFIED`，claim 已 `RECONCILED`；第二笔提交后，再扫描不改历史收据／任务版本。原严格 `xfail` 及 `--runxfail` 的 `['UNVERIFIED'] != ['SUCCEEDED']` 真实记录了**旧断言要求覆盖收据**时的失败，不得抹去或算作通过。现行断言改为：精确赢单效果晚到后，任务 GET／列表的只读 `verified_auto_wins` 显示同 `command_id`／目标 public ID 的核实证明，收据仍为 `UNVERIFIED`；核验必须匹配 claim 的 actor／指纹／目标／阶段快照，阶段版本 `v→v+1`、赢单版本 `v+1→v+2`。 | **本轮代码缺陷的定向路径转绿，不代表 C05／批次 B 整体获批**：隔离 MySQL 提交间交错核对唯一收据、原版本和三条快照；API GET／列表检查错版本／错快照不误报，50 任务列表只读一次团队策略；撤权列表旧签卡不暴露、旧 action 409。前端同版较新 turn GET 保留证明，动作历史 503 不遮蔽权威 task GET；九份客户端测试最新复跑为 131 项通过。实际 `/assistant` 页面另由 Playwright 拦截模拟 API 观察 A 处理中切至 B、B 历史未返回时无 A 进度；浏览器不接真实业务服务。上述只是隔离 MySQL、进程内 TestClient、模拟 API 浏览器和组件层结果；没有该交错的独立 HTTP／真实模型／生产事故证据。具体本轮执行输出及收集阻断见本节后续补记，§10 A–D 不变。 |
| C06 | M：`test_legacy_unattributed_claim_remains_visible_not_successful`，老 claim 无 command ID 且存在同名商机，对账只标 `UNKNOWN/legacy_unattributed`，无成功收据／效果；T03 的授权列表／裁决另测。 | 生产老 claim 的一对一人工核验未执行；**局部通过**。 |

### 9.4 R01–R04：拒绝、未知与并发恢复

| ID | 实际输入、边界与观察 | 尚未覆盖／结论 |
| --- | --- | --- |
| R01 | M：`test_r01_missing_approval_flow_rolls_back_target_create_and_receipt` 未配置审批流时**目标事务**回滚，已写活动仍在、商机及目标回执都为零；该用例不验证助手 claim 的最终状态。新增 `test_r01_started_claim_after_approval_rollback_stays_unknown_without_effect`：持久 `STARTED` 后审批事务实际回滚、零商机／精确目标效果、活动保留；到期扫描为 `UNKNOWN/STARTED`、旧 wait 未退役，人工 `REJECTED` 被拒。`test_r01_manual_rejection_requires_durable_no_call_proof_and_preserves_activity` 只有持久 `NOT_STARTED` 的无调用证明才可 `REJECTED`，旧 wait 退役、活动保留，重复裁决拒绝。O03、O06 另验证可修复表单新 wait 与 claim 前阶段过期 `SKIPPED`。 | 单次审批回滚及当前零效果不能证明其他已提交调用不存在，故 `STARTED` 不作确定拒绝；源 revision／撤权的所有组合未在一条端到端 CRM 故障场景同时覆盖；**局部通过**。 |
| R02 | M：`test_r02_c03_postcommit_response_loss_recovers_exact_stage_receipt_without_replay` 外层目标提交后响应丢失，另一会话先看到唯一 snapshot＋效果，核对后唯一助手收据；`test_r02_r03_started_lease_without_receipt_becomes_unknown_and_cannot_be_rejected` `STARTED` 但无效果证据到期后 `UNKNOWN`，再次确认与无证明 `REJECTED` 都被拒绝。 | 没有真实电源故障／数据库不可达全过程；断流浏览器也未验证 UNKNOWN 卡；**局部通过**。 |
| R03 | M：`test_r03_actual_worker_killed_after_durable_no_call_claim`／`test_r03_actual_worker_killed_after_target_transaction_recovers_exact_receipt` 子进程 `SIGKILL` 前后各一次，租约扫描发现 `CLAIMED`；持久 `NOT_STARTED` 可拒绝且零商机／效果，目标后准确效果只读补一次 `RECONCILED` 收据；`STARTED` 且无效果则保 `UNKNOWN`。A：`test_task_projection_preserves_durable_claimed_status_without_current_wait` 在无当前 wait、有历史活动与任务错误码时，公开任务 GET 仍返回 `outcome_code=CLAIMED` 和原错误码；claim 仍为 `CLAIMED/NOT_STARTED`，不凭错误推断已调用或成功。`test_projection_prioritizes_prior_unknown_over_current_claim` 在旧 `UNKNOWN`、当前 `CLAIMED` 并存时 GET 优先 `UNKNOWN`，不把旧业务收据当新命令成功。H（2026-10-03）：另起仅加载助手路由的隔离 Uvicorn 18240／18241（强制精确 3308 DSN、限定生成团队），由独立 HTTP 客户端 POST 真实签名表单，流在受控 barrier 未结束；第一条在 `settle_proposal()` 持久 claim `CLAIMED/NOT_STARTED` 后才 SIGKILL 自有服务，独立会话见 RUNNING turn、活动 1、商机／目标效果 0；手动过期本次租约后扫描两次 `[1,0]`，turn `FAILED/UNKNOWN_COMMIT_RESULT`、claim `REJECTED`、旧 wait 清除、一次 `SKIPPED` 收据，零目标写。第二条在实际 `RealCRMProposalExecutor` 的目标事务返回后、助手收据前 SIGKILL 自有服务；独立会话先见 `CLAIMED/STARTED`、一商机及精确 `(team,command,opportunity_create)` 效果，助手收据 0；过期扫描两次 `[1,0]` 后 claim `RECONCILED`、一助手收据／商机／效果、turn 仍 `FAILED/UNKNOWN_COMMIT_RESULT`。两个生成团队均清理。 | H 是固定活动及表单 fixture 的实际 HTTP→`settle_proposal()` 进程 SIGKILL，不是模型签卡、真实断电／生产负载或浏览器未知卡；接受流被阻塞而非浏览器消费；既有 M worker 仍是独立的服务 seam 探针；**局部通过**。 |
| R04 | M：`test_two_reconcilers_append_only_one_receipt` 与 `test_r04_two_manual_reconcilers_of_one_committed_receipt_only_one_settles`，两会话同时读同一目标效果，一方结算、一方已结算；仅一收据／一退役 wait／一目标 snapshot，没发第二张卡。 | 局部并发场景，未作长期 worker 压测；**局部通过**。 |

### 9.5 U01–U06：协议、断流与任务导航

V 为 `CRM-Client/tests/components/{SalesAssistantProposal,SalesAssistantProcessing,SalesAssistantReplay,SalesAssistantChat}.spec.ts` 的 mock API 组件运行，A 为 `CRM-Server/tests/unit/test_assistant_api.py` 的 TestClient；浏览器 B 的故障注入只验证对应实测时序，不能换称真实模型提案。

| ID | 实际输入、边界与观察 | 尚未覆盖／结论 |
| --- | --- | --- |
| U01 | A：`test_get_migrates_legacy_activity_wait_without_changing_frozen_command` 人工放入旧活动等待，GET 重签 union payload，冻结命令／评分不动，旧 action POST 409 附新 task，未建 turn；残缺／篡改旧卡退役。V：typed offer／form 显示和提交；逐项解析坏历史项只跳该行。H＋B：持久 form wait 的独立 task GET 200、HTTP 提交 waiting SSE 与 turn GET 一致；2026-10-03 同一隔离团队 Chromium 打开固定活动签发的 offer，点击确认进入页内 form，POST 200 后 DOM 显示已完成／活动已写入／商机已创建，同任务独立 GET／MySQL 精确效果吻合。 | **没有真实模型签发的 wait，浏览器未观察历史迁移卡**；固定候选／独立 HTTP 不能代替真实提案链；**部分通过，不批准 D**。 |
| U02 | V：A→B 导航，A 迟到 GET／stream 不覆盖 B；B GET 失败显示未打开 B 并保 A 草稿。B：5187 `/assistant` 已认证页用故障注入令 B GET 503，仍显示 A 与“未打开目标任务”；延迟 A GET 后 A→B 最终显示 B；坏历史行单行跳过。2026-10-03 专用团队另建 A/B 两任务，从 B offer 切 A offer／form 并填未提交金额 `12345`、人数 `6`，切回 B 时仍是 B 的 offer，B 自己的 form 数值为空。2026-10-08 专用 5201 `/assistant` 的**浏览器内模拟 API**：打开 A 的签名 FIELD wait，填“A的草稿”，切 B 时模拟 B GET 503；页面显示“未打开目标任务 ast_visual_b，请重试。当前视图保持不变。”，A 草稿仍在文本框、但文本框与发送按钮均禁用，显示“重试打开”；这是当时探针观察，不代表真实服务。另一专用 Vite 5202＋只读模拟 API 5203：从空视图打开 B，首次 B GET 503 后保持无当前任务；重试 B GET 200 返回模拟 `CLAIMED`，再开 B 返回模拟 `UNKNOWN`，均禁交互。**本轮新增 H＋B：**新建隔离团队 `1993`，独立业务 HTTP 18267＋实际 Chromium 5213；A→B→A 中暂扣真实 GET 200 后迟到交付，A、B 选择及 A 未提交草稿不串；分别暂扣 A、B 各一次真实 `/submit` 200 SSE，切至另一个任务再释放，另一任务聊天／处理进度不串；独立 task／turn GET 及 MySQL 确认两轮各归属原任务。详见 §9.7 后新增的同日逐步证据。 | 旧 `CLAIMED/UNKNOWN` 与 GET 503 来自只读模拟响应；新增独立 HTTP 的两个 turn 都因新团队无 AI 配置而为 `AI_UNAVAILABLE/FAILED`，目标 CRM 效果为零，不能冒充真实模型等待、成功提案或服务端故障；**A→B→A 迟到 GET／SSE 客户端归属定向通过，完整 U02 与 §10 D 仍未批准**。 |
| U03 | V：A 的 `EXPLICITLY_NONE` 加理由后转 B 的 FIELD／普通文本，B 发送不带 A choice／理由，回 A 仅同一 action 恢复；同任务 409 更换签名等待则清旧 choice 与草稿；两任务同候选 form 也不互串。B（2026-10-03）：固定来源 A form 的未提交金额 `12345`、人数 `6` 未串入 B；独立 HTTP 令 B 人数 `0` 生成 version 3 新签卡，浏览器持旧 version 2 表单提交得 409；DOM 更新为服务端人数错误／草稿，未保留旧浏览器草稿，人数改为 `4` 后 POST 200。 | 已验证固定候选 form 的 A/B 及重签隔离，**未覆盖真实模型 wait 下的 EXPLICITLY_NONE 与自由文本切换**；局部通过。 |
| U04 | V：断流后 GET 原 accepted turn／task，RUNNING 禁二次 POST；终结错误按结构化 code 补读；409 替换当前签名 wait。H＋B：现存 AI turn `atn_cafd9e53dc6b4f879e529dc423fc981f` 的独立 GET `?after_seq=0/1/100` 为 `[accepted,stage,error(AI_UNAVAILABLE)]`、`[stage,error]`、`[]`，task `error_code=AI_UNAVAILABLE`、`committed=[]`；前序浏览器仅收终结 error SSE 后 GET task／同 turn，只有一次 POST。2026-10-03 专用 A 的浏览器拦截 **客户端接收**：真实 `/submit` POST 200，响应只交付 `accepted(seq=1,turn_id=atn_9e86a5ad3a3840548bb488e1884b470b)` 帧，丢弃后续帧；浏览器随后 GET 同一 task、同一 turn `after_seq=1`（均 200），无第二次 POST，DOM 显示完成及活动／商机回执。独立 HTTP 同一 task 为 `COMPLETED/SUCCEEDED`、turn 为 `SUCCEEDED` 且事件 `[accepted,waiting]`；B 的旧签名表单另实际 POST 409 并显示服务端新卡；刷新页面后从最近任务重新打开 A，可读活动／商机回执。2026-10-04 专用隔离团队 `990129393`／Chromium 5193→独立 HTTP 18242：同任务 `ast_93ddb4b637e74fd3b75b60bb5a74b628` 点击签名活动卡，浏览器捕获一次 `/submit` POST；独立 task／turn GET 在刷新**前**确认内部 turn `atn_0d6e9ba319814b7e86120e9653688fe2` 为 `RUNNING`、事件仅 `accepted(seq=1)`。刷新时浏览器捕获该 task GET 和同一 turn `after_seq=0`、随后 `after_seq=1` 的补读，无第二次 POST；独立 GET 再证仍为 `RUNNING`、`after_seq=1` 空，页面显示已写活动／任务进行中。 | 2026-10-04 的草稿和候选来自隔离固定 fixture，内部 `RUNNING` 由**受控暂停**制造，不是物理断网、服务崩溃或真实模型耗时；浏览器网络捕获有请求清单，但响应回调未返回记录，HTTP 200／隔离标识来自另行独立 GET 和页内直接 fetch，不将其冒称逐条浏览器响应证明。终结 AI 错误不证明已提交活动或 `UNKNOWN_COMMIT_RESULT`；**部分通过**。 |
| U05 | V：活动后的 `nextTurnId` 指到同一内部 turn，刷新使用 task `processing_turn_id` GET；无指针 ACTIVE 空档只提供 GET 同步、不会无限轮询或再 POST。H＋B：固定 form wait 的先前独立 fixture 有一成功表单 turn 与一成功 `continue_proposals` turn；2026-10-03 专用团队 offer→form 的浏览器 POST 200、完成 DOM 与同任务独立 GET `COMPLETED/SUCCEEDED`、活动／商机收据、MySQL 精确目标效果一致；另一 A 任务丢 SSE 后补读其已成功 turn，刷新重开已完成任务仍有回执。2026-10-04 同一新建任务 `ast_93ddb4b637e74fd3b75b60bb5a74b628`：原确认 turn `atn_1a0d8b95eb3745f6b589bd5f0fb13320` 的 `waiting(seq=4).next_turn_id` 指向内部 `continue_proposals` turn `atn_0d6e9ba319814b7e86120e9653688fe2`；刷新前后 task 的 `processing_turn_id` 不变且 status=`RUNNING`，内部事件为 `[accepted(1)]`。独立 MySQL 前后均仅一条该团队／客户活动 `990130111`（`ASSISTANT_2`），无第二次写入；释放暂停后原内部 turn `SUCCEEDED`、`[accepted(1),waiting(2)]`，task `ACTIVE`／当前 wait `proposal:opportunity_create`、活动回执仍在，浏览器出现“根据这次活动，为客户创建商机吗？”与“填写商机信息”。 | 2026-10-04 验证的是固定草稿、规则候选和受控内部暂停下的**真实浏览器刷新恢复**，并非模型完成活动、真实故障或生产环境；没有验证真实模型生成候选／评分→活动→提案，也未在此验收中提交商机表单；**局部通过，不批准 D**。 |
| U06 | V：成功拒绝提案仍是普通消息，无 FailureCard；取消后已有活动仍展示“活动已写入”，失败卡按 typed committed 区分先前活动，历史收据徽标用目标 ID 而非中文子串。B：前序 `AI_UNAVAILABLE` 失败卡显示“处理失败，请查看任务状态”，未误称活动已写；2026-10-03 同团队固定 offer 拒绝后 task 为 `COMPLETED/REFUSED`、保留原活动、无第二商机；另一任务取消后页面仍显示“活动已写入”。 | 拒绝／取消已走持久隔离任务的浏览器，但候选非真实模型，未走所有失败文案分支；**局部通过**。 |

### 9.6 D01–D04：事实更正、补充与重评分

| ID | 实际输入、边界与观察 | 尚未覆盖／结论 |
| --- | --- | --- |
| D01 | 单元：`test_date_correction_keeps_only_friday_executable_and_old_quote_auditable`／`test_confirmation_uses_corrected_due_without_reviving_old_date`，原句“周三我发方案”、后句“不是周三，是周五”，同一 action ID、旧 evidence `superseded_by` 新 evidence，冻结来源两句、唯一有效 due 为 `2026-10-02T23:59:59`；模型仍返旧周三也由用户更正覆盖。 | 固定结构化结果非真实模型；对应真实下游任务仅通过定向候选／执行测试覆盖，未走实际 Web 全链；**局部通过**。 |
| D02 | 单元：`test_owner_action_and_date_corrections_preserve_identity_and_other_action`／`test_independent_owner_then_action_then_date_corrections_share_one_identity` 分别一次和逐句改负责人、动作、日期，原行动 ID 保持，其余行动不受影响；`test_explicit_customer_correction_retires_old_card_and_writes_only_new_customer` 换客户重签、重评分，只往新客户写一活动，歧义／无权／未找到不退回旧绑定。 | 更正使用测试构造结构化回复和单元 DB，非真实模型／UI；**局部通过**。 |
| D03 | 单元：新增 `test_low_score_field_supplement_rescores_full_canonical_activity_before_single_real_write` 同一 coordinator／SQLite 会话：固定 structurer／gate 对原话评 42 并签 `FIELD`，独立读零活动；补充交付风险后对**原话＋补充**和合并 canonical `content_json` 重评 78，确认卡及冻结命令分数／来源一致，补充前仍零活动；确认使用 `RealActivityWriter` 仅写一条最终内容／来源／分数为 78 的活动，structurer 与 gate 各仅调用两次，确认时零模型调用。原有 `test_field_supplement_merges_canonical_facts_and_freezes_rescored_full_source` 也以固定 RecordingGate 核对评分及模型元数据；`test_supplement_low_score_clears_old_score_and_asks_new_gap` 覆盖旧分 82→42 的另一路径。`test_high_gate_score_never_bypasses_missing_next_action` 追问缺失下一步；`test_explicit_absence_preserves_user_reason_without_inventing_next_action` 保留明示暂无及理由；`test_unparseable_time_asks_only_for_time_before_freezing` 追问时间。 | `<60→补充→>=60→确认` 是进程内固定模型输出和真实活动 writer 的局部链，非在线评分、独立 HTTP 或浏览器；“继续跟进”等非空模糊下一步在在线高分下仍未验；**局部通过**。 |
| D04 | A＋单元：`test_get_migrates_legacy_activity_wait_without_changing_frozen_command` 的 409 来自**旧 wait 经 GET 迁移后**提交旧 action。新增 `test_real_api_correction_retires_old_signed_card_and_writes_one_corrected_activity` 在**同一文件型 SQLite TestClient／真实 coordinator、worker 与 `RealActivityWriter`**：原正文评分 85，用户沿原卡更正预算 100 万→80 万，新卡 action／fingerprint／submission ID 均改变、完整来源重评 78；用新的请求键提交旧 action POST 409、返回最新卡、该旧卡请求键无 `AssistantRequest` 记录且零活动；新 action 确认 200 后独立会话仅一条 80 万正文／两段原文／分数 78 的 2.0 活动。固定 structurer／gate 代替模型，权限／操作日志／向量 adapter 为 stub，文件型 SQLite 不兼容的独立 stage telemetry 禁用；不等于独立 HTTP 或浏览器。`test_explicit_content_correction_retires_card_without_rebinding_customer`／`test_explicit_customer_correction_retires_old_card_and_writes_only_new_customer` 在 coordinator 层覆正文／换客户重签；`test_change_kind_resets_typed_content_preserves_sources_and_denies_committed_or_active` 拒绝已提交后改类型。 | 同链 TestClient 旧卡 409 与唯一活动已验证；尚无真实模型／实际浏览器同链观察，不能用进程内 API 冒称独立 HTTP；**局部通过**。 |

### 9.7 T01–T04：日期归属、人工核对、回滚

| ID | 实际输入、边界与观察 | 尚未覆盖／结论 |
| --- | --- | --- |
| T01 | 单元：`test_retry_uses_first_received_anchor_across_midnight` 首次 2026-09-30 23:59、重试 10-01 00:01，同一原句／行动与 `anchor_at=2026-09-30T23:59:00`、`timezone=Asia/Shanghai`、`granularity=DATE`、parser 版本及 `due_at=2026-10-07T23:59:59` 保持稳定；`test_confirmation_uses_canonical_quoted_action_due` 冻结原话日期，无需原句含 ISO。新增 `test_signed_midnight_retry_keeps_original_due_anchor_through_task_commit` 用固定结构化输入“我下周三发方案”跨午夜重试，保留原行动 `item_id`、来源片段／锚点／时区／粒度／解析版本，冻结活动命令并按该冻结内容**由测试构造活动行**，签发 canonical 任务候选后用 `RealCRMProposalExecutor` 提交唯一 `FollowUpTask` 与 `CREATED` 事件；任务 due 为 2026-10-07 23:59:59、证据原句及锚点一致，下一轮无候选且最终任务／事件均各一条。`test_corrected_action_uses_only_current_friday_evidence` 另验证更正周五后的单条任务。 | 跨夜原句→固定 canonical→候选→真实任务目标执行在进程内完成，但活动行是按冻结命令由测试构造，非在线模型或独立 HTTP 完整活动写入链；纯日期映射 `23:59:59` 的业务政策仍未批准；**局部通过**。 |
| T02 | 单元：`test_vague_due_expression_never_gets_invented_iso` 的“月底左右”=`AMBIGUOUS`、“有空”=`UNRESOLVED`，`due_at=null`；`test_unanchored_or_unquoted_model_date_is_not_executable` 与虚构动作动词测试均无可执行日期；`test_ambiguous_canonical_action_due_cannot_freeze_confirmation` 等待补日期、无冻结命令。 | 未由实际 HTTP／UI 验证所有无行动归属变体的最终任务写入数；**局部通过**。 |
| T03 | M＋A：`test_owner_only_listing_and_team_operator_filters_without_payload_leaks` 同团队普通成员只见本人、team scope／跨团队 403；授权运维仅本团队分页最小字段、跨团队记录不泄漏；`test_similar_crm_row_cannot_prove_success_or_rollback_but_preinvocation_can_reject` 同名对象不能判成功／拒绝，确切 `NOT_STARTED` 才拒绝且审计；`test_real_target_creation_receipt_allows_only_one_audited_success` 精确创建收据仅容一次授权成功。H：新增独立隔离 Uvicorn `127.0.0.1:8020`、独立 HTTP 客户端和隔离 MySQL 业务身份探针：构造真实团队成员／授权运维及 `UNKNOWN` claim，owner／授权 team 非空 GET 都 200 且仅最小字段；其他 owner 空、普通成员 team 403、跨团队 operator 403；无目标效果时 SUCCEEDED／REJECTED 各 409，目标 CRM 创建事务写精确回执后，错 public ID 409、正确证据 200、重复裁决 409；独立会话核一商机／一效果／一助手收据／一审计动作，临时数据已清理。 | H 的 claim 由持久测试数据构造，并非真实模型／未知提交事故；不是生产老 claim 人工核验，也未验证运维 Web 页面；**局部通过**。 |
| T04 | M＋A：`test_t04_rollback_preserves_activity_exact_target_receipt_and_readable_old_profile` 同时关新提案／旧发表后，新稿不签发 offer，原活动、旧版指针及精确效果仍可读；TestClient profile GET 200／`STALE` 且不含 2.0 私有活动；恢复后只发表新合格版。`test_t04_unknown_claim_blocks_offer_even_with_proposals_disabled_and_remains_owner_visible` 验证 UNKNOWN 阻断新命令且 owner 可读。H（2026-10-04，**独立隔离服务进程**，专用团队 `990129394`，仅 `127.0.0.1:3308/crm_assistant_acceptance`）：开关全开 PID `81521` 时，用 `/tmp` 验收包装器的 `/acceptance/publish` 发表旧档案 v1 `cpv_dfee753dac374a509c02abc674496271`；真实认证 task／profile GET 分别为 `ACTIVE/OFFERED`、`200/READY/v1`。停进程，以双开关关闭的 PID `87364` 重启；真实认证 GET 仍可读原签卡和旧档案 `200/READY/v1`。原签卡经真实 `/submit` HTTP 200 进入 `FORM_DRAFT`，随后拒绝，零商机；关闭期间 `/acceptance/publish` 两次返回 `PROFILE_PUBLICATION_DISABLED`。加入一条旧合格活动与一条**固定草稿、非真实模型**的 2.0 活动：后者真实 `/submit` HTTP 200、turn `SUCCEEDED`、任务完成而无新 offer；独立 MySQL 核 4 条活动／3 个 turn／累计 1 个关闭前 offer／0 商机、仅旧档案 v1；认证 profile GET `200/STALE/v1`，只含已发表的旧原句，不含两条新增活动。再停进程，以双开关打开的 PID `7496` 重启：验收包装器发表 v2 `cpv_080a25e9a20a47c6a289cdc04ec58a13`；真实认证 profile GET `200/READY/v2`，包含新增旧合格来源、不含 2.0 来源；另一个固定草稿经真实 `/submit` HTTP 200 重新签发 `ACTIVE/OFFERED`，拒绝后零商机，独立 MySQL 此时 5 活动／9 turn／累计 2 offer／2 档案版本。额外**已签卡目标执行探针**：全开 PID `30104` 签发有效商机卡 `ast_0ee96274fb9f43d6ad37b407a80ae201`，停进程后双关 PID `32763` 仍接受真实认证 offer 确认和完整表单 `/submit`（均 HTTP 200）；turn `atn_f0c0142bf92e408db9d5eaaceaa0f310` 为 `SUCCEEDED`，task `COMPLETED/SUCCEEDED`，MySQL 精确核一商机 `opp_7b8504b63bd34b6c86b171db3afc842c` 与一命令效果；最终专用团队 6 活动／12 turn／累计 3 offer／1 商机，档案 `200/STALE/v2` 仍不含新 2.0 活动。 | **局部通过，不批准 D**。两个开关是进程级环境设置，非按团队灰度；新提案开关只挡下一次 `offer_next_proposal()`，不撤销已有签卡，也不阻止它在关闭后执行真实 CRM 写入，故不能宣称“关闭即停止所有新商机”。`/acceptance/health`、`/acceptance/offer` 和 `/acceptance/publish` 均为 `/tmp` 验收包装器入口，**不是生产 HTTP API**；任务／turn／档案 GET 及 `/submit` 为真实认证路由。固定草稿、规则候选和隔离库不等于真实模型／生产流量；无团队灰度、部署监控指标或生产回滚证据。发布前须明确旧签卡撤销／冻结策略并在实际部署链验证，不以本探针批准 A–D。 |


**2026-10-04 T04 团队共享回滚栅栏续验（隔离库／固定候选，A–D 均不批准）：**仅在 `mysql+pymysql://root:assistant-test-only@127.0.0.1:3308/crm_assistant_acceptance`、`RUN_MYSQL_INTEGRATION=1` 使用专用团队 `990129909`、独立 HTTP `127.0.0.1:18243` 与 Chromium `127.0.0.1:5194`；验收包装器限定团队／DSN，`/tmp` 状态含认证材料，本文不记录 token。原任务 `ast_01c393732568495fb45b242b89b70ec2` 的 generation 1 签卡在团队停用至 generation 2、专用 HTTP 服务重启后，认证 GET 为 `ROLLED_BACK`、无 waiting、`proposals_enabled=false`；旧 action 经 POST 为 `409`，原任务仍一条已写活动、零 command claim／零 CRM effect／零商机。策略恢复至 generation 3 后，旧 action 仍 `409`；显式 `resume_proposals` 返回 `accepted`／`waiting`，独立会话核对新签卡 generation 3、原任务零 claim。再次停用至 generation 4 后新卡退役，认证 GET 为 `ROLLED_BACK`、version 4、waiting 空；恢复至 generation 5 后仍不自动复活，须再次由专用浏览器点击“重新检查后续建议”。点击后认证 GET 为 `OFFERED`、version 5、新 action 与原 generation 1 不同、无运行中的 turn；旧 action 再 POST 为 `409 STATE_CONFLICT`。Chromium 在停用时观察两张旧卡“已撤回”、暂停提示与显式重查按钮；点击及重新打开任务后观察“下一步建议”／“填写商机信息”新卡，按钮不再显示。浏览器开发服务曾反复导航，DOM 不是唯一凭据：以独立 HTTP GET 与 MySQL 签卡代次／零 claim 为最终核对。

**同团队精确回执边界：**另外构造的受控 `STARTED` 阶段命令 `asa_3ff57e71e3ee47478f2bfcd97c28c267` 仅凭目标事务中同一 `command_id` 的一条效果及阶段 snapshot 对账为 `RECONCILED`，原任务以外的探针任务仅有一条助手收据；无目标回执的 `STARTED` 创建命令 `asa_3b074e7cc1fd4b9e8d74033636fd5a54` 为 `UNKNOWN`、匹配效果零。最终独立、团队限定查询：原任务 version 5／签卡 generation 5／command claim 零；团队另有探针目标效果一、商机一，**不得归于原任务旧卡**。旧 `UNKNOWN` 的有界周期重查可在稍后实际目标回执提交后核对，但无证据仍维持 `UNKNOWN`，绝不补发目标操作。受控探针和固定候选不等于真实模型或生产未知提交事故。

**回归与边界：**隔离环境运行 `CRM-Server/venv/bin/python -m pytest -q --no-cov --tb=short` 加七个指定 MySQL 场景文件（上文执行基线列出的文件），首次 `84 passed, 1 failed`（`test_third_party_stage_change_is_not_assistant_effect` 的扫描计数偶发 0），该用例独跑 `1 passed`，随后整组复跑 `85 passed, 69 warnings`；加入取消时释放跨进程栅栏的回归后，测试先红（worker session 未关闭），修复 `execute_turn` 的 `proposal_stack.aclose()`／`db.close()` finally 顺序后单测 `1 passed`、整组 `86 passed, 70 warnings`。`test_assistant_api.py`＋`test_assistant_proposals.py` 本次 `114 passed, 114 warnings`；此前前端定向 `42 passed`。`ruff check` 覆盖四个相关 Python 文件退出 1，包含历史长行／导入风格诊断；本轮前端 `npm run type-check` 曾退出 2（12 个无关文件共 42 项诊断），**不得记为静态检查通过**。未做真实模型生成签卡、生产存量 claim 盘点／停电、长期多 worker 压测或跨版本全量浏览器回归；现有 A–D 发布门禁仍未批准。

**专用资源清理：**关闭本轮两个 Chromium tab 与专用 5194／18243 进程后，由仅绑定该团队的 fixture 控制器返回 `{"cleaned":true}`；独立、按 `team_id=990129909` 查询任务、动作、CRM 效果、策略、商机均为 0，控制器随后停止；本轮 `/tmp/crmwolf_rollfence_accept_1004_*` 文件已删除。未停止共用服务、未处理其他团队数据。

**执行基线与限制（2026-10-02）：**只在 `DATABASE_URL=mysql+pymysql://root:assistant-test-only@127.0.0.1:3308/crm_assistant_acceptance RUN_MYSQL_INTEGRATION=1` 跑七个 MySQL 场景文件（`test_customer_profile_source_scenarios_mysql.py`、`test_deal_journey_source_fence_mysql.py`、`test_assistant_command_effect_scenarios_mysql.py`、`test_assistant_opportunity_scenarios_mysql.py`、`test_assistant_command_recovery_scenarios_mysql.py`、`test_assistant_operator_scenarios_mysql.py`、`test_assistant_rollback_scenarios_mysql.py`），前次 `72 passed, 62 warnings`；后端六个定向单元文件（`test_assistant_proposals.py`、`test_assistant_intake_corrections.py`、`test_assistant_api.py`、`test_assistant_reconciliation_permission_migration.py`、`test_assistant_crm_target_effects.py`、`test_customer_product_intent.py`）前次 `181 passed, 115 warnings`；前端九个助手 Vitest 文件前次 `104 passed`。空 `VITE_API_BASE_URL` 的 SSE 提交曾错走 `/v1/` 而 task GET 走 `/api/v1/`，回归测试修复前红、修复后绿；Chromium 5189 同源代理观察实际 POST 200 到 `/api/v1/.../submit` 并在该浏览器 DOM 看到完成回执文本，截图超时未取得。另一个已清理 fixture 的独立 GET／MySQL 读回完成任务、活动＋商机回执、一次表单 turn／一次合法内部 turn、一商机和唯一精确效果；这些结果不视为本次浏览器的数据库观测。多次页面同 URL 重载／frame detach 曾短暂显示未登录，未据此推断持久认证故障。签卡仍是固定候选，隔离团队真实模型 turn 返回 `AI_UNAVAILABLE`。本次 fixture 退出码 0、发出 `RECEIPT_BROWSER_CLEANED`；隔离库核 team `990129027`／user `990128205` 的 request／turn／action／task／活动／客户／商机／效果／用户／团队行归零；本次 5189 前端代理及 tab 已释放，8020 隔离 API 保留。`npm run type-check` 前次仍有其他文件 42 项诊断，未报告全局构建通过；`npx eslint src/api/assistant.ts` 前次通过，测试文件不在 ESLint `parserOptions.project` 内，直接 lint 测试文件报解析配置错误；此前 Ruff 定向诊断未消除。本组验证不是全项目测试、生产存量审计或真实模型验收。

**2026-10-03 同团队补充验收与清理：**独立专用隔离团队 `990129314`／用户 `990128399`，仅指向 `127.0.0.1:3308/crm_assistant_acceptance`；5191 Chromium 指向共用隔离 API 8020。同一持久任务 `ast_9a0506a901894427bdf3639220459075` 实际经过固定来源 offer→页内表单→POST 200→完成回执；独立 GET 和 MySQL 精确 `command_id`、目标 public ID 核对同一条创建效果。另一任务 `ast_2d59fa7b18324c46b46713834ceb2196` 拒绝后活动保留且无第二商机；`ast_76a14288587f4a2081f6497131b9ca81` 取消后仍见已写活动。A/B 两个额外任务验证未提交表单草稿不互串、B 旧卡 409 返回服务端新签名／错误草稿并能修正成功；A 的客户端故障注入只交付 `accepted(seq=1)`，丢弃流尾，浏览器后续仅 GET task／原 turn `after_seq=1`，未重发 POST，恢复完成回执；独立 GET 原 turn 为 `SUCCEEDED`、事件 `[accepted,waiting]`。**故障注入只改变浏览器收到的 SSE，不等于服务端崩溃或真实网络事故。**刷新后的完成任务从最近任务重开可读活动／商机，但未在内部 turn 运行时刷新。定向新跑：后端六个单元文件 `181 passed, 115 warnings`，七个指定隔离 MySQL 文件 `73 passed, 62 warnings`（均 `python -m pytest -q --no-cov`），前端九个助手 Vitest 文件 `104 passed`；未运行会取消其他 ACTIVE 任务的 `assistant-design-scenarios.spec.ts`，也未声称全项目类型检查／构建通过。专用 fixture 退出未打印 `FIXTURE_CLEANED`，故先验证生成团队所有权、专属用户邮箱／角色／业务资产，再按团队及客户在**单个事务**删除专属数据（包括异步产生的 enrichment job／profile current／journey）；独立新会话复核 87 张有 `team_id` 表对该 team 合计 0 行、团队／用户／角色／客户及 turn events 均 0。专用 token／fixture 文件、两个 tab、5191 服务已移除；共用 8020 API 保留。下述门禁不把该固定候选与隔离数据升级为真实模型／生产存量证据。

**2026-10-07 定向补验（只补 §9，不批准 §10 A–D）：**专用团队 `402`／任务 `ast_989ca79706744bab9508057e8b13cec0` 仅使用隔离 `127.0.0.1:3308/crm_assistant_acceptance`、专用独立 HTTP `127.0.0.1:18246` 与 Chromium `/assistant`（5197）。候选是持久固定候选，非在线模型生成；该团队未配置 `AIConfig`。浏览器实际确认 offer、进入页内表单并提交；独立 HTTP 与 MySQL 对同任务核得已写客户活动 `470`、商机 `opp_6b62dc12fe994dbfa7e96f3834a9accc` 和唯一 `opportunity_create` 目标效果，效果关联 `command_id=acm_b4028f21eea043eab306358550fda67a`，不能将同名对象或只读任务状态冒充目标效果。独立 HTTP 重交旧签卡为 `409 STATE_CONFLICT`；内部后续 turn 因 `AI_UNAVAILABLE` 失败，重查后的任务 version 7 仍为 `ACTIVE/error_code=AI_UNAVAILABLE/processing_turn_id=null`，两个失败 turn 为 `FAILED`。浏览器 DOM 显示活动已写入、商机已创建、后续处理失败和“重新检查后续建议”；独立 MySQL 仍仅一商机、一目标效果，失败没有回滚已提交活动或重做商机。此链**不证明真实模型提案或内部 turn 成功**，也未新测同链浏览器断流、切任务或 `STARTED→UNKNOWN`。原 tab 曾反复导航 `/login`、截图超时；新增 tab 页面为空且观察期间文档替换报错，不将导航稳定性或最新输入修复记为浏览器通过。

**2026-10-07 回归边界：**更正隔离 MySQL 回滚测试的伪造活动指纹 fixture，保持生产侧签名和来源校验不放宽；七个指定 MySQL 场景文件合跑 `86 passed, 173 warnings`。修正 canonical `_merge_actions()` 对“已有同一行动、旧日期证据 `UNRESOLVED`，后来用户明确原句补足日期”的跳过：回归先红后绿，同一行动 ID 获得可解析的新日期且保留两句来源；六个后端定向单元文件合跑 `199 passed, 121 warnings`，并非真实模型或 Web 更正链。客户端修正重开 `ACTIVE`／无 wait／无 `processing_turn_id` 任务时凭空设置 pending 导致输入锁死，以及 `STRUCTURING_UNAVAILABLE`／`QUALITY_GATE_UNAVAILABLE` 且无 wait 时不可重新输入；三条组件回归先红后绿，九个助手 Vitest 文件 `125 passed`。删除“无处理指针的 ACTIVE 必须锁定”的旧断言和“FIELD wait 显式 `confirmation_payload:null` 必须拒绝”的旧断言：前者固定错误行为，后者与双端合同相反。新客户端分支**仅有 mock API 组件验证**，本次旧浏览器 tab 的 `AI_UNAVAILABLE` 卡和新 tab 空页面不能证明其真实 UI 输入恢复；独立 HTTP／浏览器对相应可恢复错误和拒绝活动确认后重开仍待补验。`npm run type-check` 退出 2（12 个其他文件共 42 项诊断，未列本次助手组件）；聚焦三个后端改动文件的 `ruff check` 退出 1（93 项诊断，含既有样式和测试中文标点），不得宣称全局静态检查通过。
组件定向 `npx eslint src/components/sales-assistant/SalesAssistantChat.vue` 退出 0，报告 `0 errors, 4 warnings`（nullable boolean 条件，464／892／911 行）；这不是项目全量 lint 通过。额外重开 5197 Vite 两次尝试最新输入分支的**浏览器内模拟 API** 验证：首次请求拦截清理报错、随后观察超时，第二次改用专用模拟 API 18247 后 Chromium 文档导航持续销毁执行上下文；两次均未形成可用 UI 证据，已释放 tab、停止新增专用 Vite／模拟 API、删除临时模拟文件，不能把组件单测视作真实浏览器通过。收尾聚焦复跑 `SalesAssistantChat.spec.ts` 为 `20 passed`，`test_later_explicit_due_resolves_same_action_without_changing_its_identity` 为 `1 passed, 46 deselected, 22 warnings`；均只证明其指定路径。

**2026-10-07 来源归属复核补验（仅后端固定结构化输入，不提高 §10 门禁）：**只读审查指出 canonical `_merge_actions()` 的三类误归属：同批重复行动生成多条 active evidence、两项行动共用“下周三”时错取另一子句、旧负责人已有原文依据但后句仅补“下周三发方案”时仍不解析。分别补可先红的回归并修正：追加新证据后同步更新本批 active；按行动＋负责人优先选日期／动作／负责人子句；只有先前原文锚定且该动作在旧行动中唯一时，才允许无负责人日期句继承负责人。“李经理下周三发方案”不得借用旧“我”的负责人；两位负责人都曾“发方案”时，无负责人新日期不得同时授予两项（该负例先红后绿）；同动作两负责人在**各自子句**明确给出“下周三”时仍分别解析（先红后绿）；仅第二位负责人明确日期时，即使模型遗漏第二条行动，也不得把该日期授予第一人（先红后绿）；同句仅一名负责人明确“发方案”、后句无负责人补日期时可承接（先红后绿）。最终六个受影响助手单元文件合跑 `191 passed, 115 warnings`；七个指定隔离 MySQL 场景文件仅连 `127.0.0.1:3308/crm_assistant_acceptance`、`RUN_MYSQL_INTEGRATION=1` 合跑 `86 passed, 173 warnings`。聚焦 `ruff --select RUF021` 通过；两文件完整 `ruff check` 仍退出 1（89 项诊断），不得称静态检查通过。此补验不含在线模型、独立 HTTP 或浏览器；前述专用团队 `402` 已清理，不复用旧任务，不以本段补齐历史待发布副本 SELECT-only 来源审计、真实模型链、日期业务政策或 U01–U06 同链故障 UI。

**2026-10-07 来源归属再复核与客户端视觉探针（仅定向证据，§10 A–D 不批准）：**针对同一负责人先说“李经理发方案”、后在另一子句明确说“李经理下周三发方案”，新增回归先红（日期误标 `UNRESOLVED`）、后绿（同负责人明确日期 `RESOLVED`、`2026-10-07T23:59:59`）；仅当后一子句没有该负责人时才走跨子句防串用限制，其他负责人日期不得借用。最终六个指定助手单元文件合跑 `192 passed, 115 warnings`；七个指定隔离 MySQL 场景文件仅指向 `127.0.0.1:3308/crm_assistant_acceptance`、`RUN_MYSQL_INTEGRATION=1` 合跑 `86 passed, 173 warnings`；聚焦 `ruff --select RUF021` 通过，两文件完整 Ruff 仍退出 1（90 项诊断：RUF001 75、E501 10、I001 3、F401 1、RUF003 1）。客户端 `SalesAssistantChat.spec.ts` 定向复跑 `20 passed`。另用专用 5199 Vite／Chromium 和**浏览器内模拟 API**打开 `/assistant`，观察到最近任务 A／B；点击 A 时 Chromium `Runtime.callFunctionOn timed out`，之后执行上下文持续因导航销毁，**未观察到任务重开后的输入可用，更未执行 A→B 切换或独立 HTTP／真实模型同链验证**。专用 tab／Vite 均已释放／停止；该探针不提高此前 U01–U06 或 §10 D 的浏览器结论。前述团队 `402` 未复用，历史副本 SELECT-only 审计、真实模型提案／评分及纯日期到期政策仍缺。

**2026-10-07 专用资源清理与门禁：**释放两个专用 Chromium tab，停止 18246／5197 专用服务，**未停止共用隔离 MySQL**。按已核对团队名、owner 邮箱及客户／产品／采购方式／角色 ID，只在上述隔离库以单事务删除团队 `402` 的 fixture 和派生行；未删除由其他角色共用的三项全局 permission。新建独立 MySQL 只读一致快照逐一核查 89 张带 `team_id` 表均对该团队为零（合计零行），turn events、team、user、role、customer、product、method、原任务、原商机、原 command 效果和该 role 的 permission 关联亦均为零。历史待发布副本 SELECT-only 来源审计、真实在线模型提案与评分、相关日期业务政策及完整 U01–U06 浏览器故障链仍缺；不得由本次局部定向结果提高 A–D 发布结论。

**2026-10-08 本轮定向复核（只更新 §9，§10 A–D 均未批准）：**六个指定后端助手单元文件此前合跑 `223 passed, 121 warnings in 11.99s`；新增合法句式回归后重新合跑 `224 passed, 121 warnings in 12.41s`，随后强化同一测试的跨轮 `item_id` 断言并聚焦复跑 `2 passed, 70 deselected, 22 warnings in 1.02s`。另跑 `test_assistant_confirmation_contract.py`、`test_assistant_intake.py`、`test_assistant_quality.py`，此前 `55 passed, 58 warnings in 3.97s`、本次复跑 `55 passed, 58 warnings in 3.53s`。七个指定隔离 MySQL 场景文件仅以 `RUN_MYSQL_INTEGRATION=1` 指向 `127.0.0.1:3308/crm_assistant_acceptance`，此前 `86 passed, 173 warnings in 22.66s`、本次复跑 `86 passed, 173 warnings in 25.43s`；九个指定前端助手 Vitest 文件为此前的 `125 passed`，后续后端边界修正未复跑前端。这些是不同测试集合／层级，不能相加宣称在线评分、独立 HTTP 或真实浏览器链通过。`_owner_mentioned()` 的三例固定结构化归属回归先红后绿：“李经理会计下周三发方案”、“李经理发小下周三发方案”、“我嫂下周三发方案”不能借短负责人解析日期；“讨论后李经理下周三发方案”、“请李经理在下周三发方案”仍为正例。补验先说“李经理发方案”、后说“李经理会在下周三发方案”：先红时 owner quote 仍是旧原句，后绿时新 quote 解析至 `2026-10-07T23:59:59` 且跨轮原 action `item_id` 不变；这是限定句式修正，不构成中文称谓／语法穷尽证明。两文件聚焦 Ruff `--select RUF021` 退出 0，但此前完整 Ruff 退出 1，不能称整体静态检查通过。专用 5201 Chromium `/assistant` **浏览器内模拟 API**确见 A FIELD 草稿填入后 B GET 503、失败提示、保留 A 草稿及旧视图，且输入／发送被禁用、可点“重试打开”；并无独立 HTTP、真实模型或该浏览器任务的 MySQL 效果证据。后续尝试 `CLAIMED/UNKNOWN` 的拦截探针中断／超时，**不得记为两状态浏览器通过或请求次数证明**；无既有视图的 503、可恢复错误与断流补读也未在本轮形成可靠新增浏览器证据。专用 tab 已释放、5201 Vite 已停止，未停止共用隔离 MySQL。历史待发布副本 SELECT-only 来源审计、真实模型提案／评分、商机去重业务阈值及纯日期政策仍为门禁缺口；团队 `402` 已清理，本轮未复用。

**2026-10-08 负责人日期再复核（固定结构化输入，§10 A–D 仍未批准）：**代码审阅发现“李经理会在下周三提醒王经理发方案”也会因同子句含“发方案”而给李经理旧行动错误解析日期。跨轮回归先红：旧证据 `UNRESOLVED` 被该句替换成 `RESOLVED/2026-10-07T23:59:59`；收紧负责人后日期与本人动作的邻接条件后，该句不再替换原证据，合法“李经理会在下周三发方案”仍解析并沿用行动 `item_id`。新负例及两项正例聚焦复跑 `3 passed, 70 deselected, 22 warnings in 0.94s`；最终六个指定助手单元文件 `225 passed, 121 warnings in 11.08s`，补充三文件 `55 passed, 58 warnings in 3.90s`，七个指定隔离 MySQL 文件仍仅指向 `127.0.0.1:3308/crm_assistant_acceptance`、`RUN_MYSQL_INTEGRATION=1`，合跑 `86 passed, 173 warnings in 22.31s`；两文件聚焦 `ruff check --select RUF021` 退出 0。未补在线模型、独立 HTTP／新浏览器链、历史待发布副本 SELECT-only 来源审计、商机去重阈值或纯日期政策；§9 此处仅为针对反例的定向证据，不提高发布门禁。

**2026-10-08 D03／D04／T01／R01／C05／U02 定向验收补记（仅 §9）：**最终聚焦复跑 D03 的低分补全真实活动 writer、D04 的同链 TestClient 更正旧卡、T01 的跨夜 canonical 任务目标执行：`3 passed, 63 warnings in 5.84s`。隔离 MySQL `127.0.0.1:3308/crm_assistant_acceptance`、`RUN_MYSQL_INTEGRATION=1` 聚焦复跑 C05 提交前故障、提交后响应丢失、提交间扫描反例及 R01 审批回滚后 `STARTED`：当时为 `3 passed, 1 xfailed, 33 warnings in 3.71s`；另用 `--runxfail` 复现历史严格断言 `['UNVERIFIED'] != ['SUCCEEDED']`。该断言要求将已结算阶段的只增收据覆盖成 `SUCCEEDED`，**当时的红灯事实保留，但不能再解释为现行 C05 晚到证明缺失**；现行合同是不改写原 `UNVERIFIED` 收据，通过同一命令、操作者、指纹、目标、阶段快照及连续版本的目标效果生成只读 `verified_auto_wins`，不凭最终 `WON` 推断成功。U02 补验由临时 `/tmp/u02-playwright-probe.mjs`、`/tmp/u02-mock-api.mjs` 和三张 `/tmp/u02-navigation-{failed,claimed,unknown}.png` 记录，是实际 headless Chromium 对**只读模拟 API**的空视图→B 503→重试 `CLAIMED`→再开 `UNKNOWN`；本轮重跑的逐态 DOM／输入禁用值、GET 503／200／200 请求日志及零页面错误显示：失败时空视图和“重试打开”，两种核对状态下 B 为当前任务、显示禁重复提交警告且输入禁用。模拟 API 拒绝写请求，其他不相关页面请求可返回 404／405；它不是实际业务服务或 A/B 迟到竞争。当时客户端 `SalesAssistantChat.spec.ts`＋`SalesAssistantProposal.spec.ts` 定向复跑 `54 passed`，仅为 mock API 组件层。临时探针未入库，复核以本节输入／状态及既有 V 用例为边界，不能当作持久回归测试。上述 D03／D04 用固定模型输出，T01 活动行按冻结命令由测试构造；没有在线模型提案／评分、独立 HTTP 全链、历史待发布副本 SELECT-only 来源审计、获批的商机去重阈值与纯日期 `23:59:59` 政策。本轮未复用已清理团队 `402`、未对生产执行写入；§10 A–D 保持未批准。

**2026-10-08 C05 修复后定向复核（仅 §9，未改变发布门禁）：**进程内 `test_assistant_api.py` 为 `54 passed, 70 warnings`；仅在 `127.0.0.1:3308/crm_assistant_acceptance` 运行四份命令效果／恢复／运维／回滚 MySQL 场景为 `41 passed, 133 warnings`，含提交间结算一次、目标赢单晚到后的只读精确证明以及原收据／任务版本不变。九份客户端助手 Vitest 最新复跑 `131 passed`，覆盖同版本旧 turn GET 不擦除较新 task GET 证明、B 历史延迟时立即移除 A 收据与处理提示／阶段进度、打开 B 失败仍可对 A 的有效等待输入；删除旧测试中要求失败打开 B 后隐藏 A 操作的错误断言。A 处理中、B GET 已成功但历史未返回时 A 进度残留的回归先红（实际提示“Agent 正在处理”出现在 B 下），修复后单测和九文件复跑转绿。实际 `/assistant` 页面上的 headless Chromium **连接只读模拟 API，非业务服务**：阶段收据 `UNVERIFIED` 且无证明时不显示赢单证明、同命令证明晚到后显示“自动赢单已核实”、历史 GET 503 后仍显示；模拟 A→B 请求中 B GET 503 时 A 的待发送文本保留且输入可用，重试 B 后在 B 动作历史未返回时 A 收据不再显示，页面 JS 错误为零。另以 Playwright 驱动现有 5173 `/assistant` 页面：拦截 A 的模拟 POST 而**不转发目标业务服务**，保持模拟处理流未结束；B GET 成功但 B 动作历史 GET 未返回时，页面显示 B、无“Agent 正在处理”／A 阶段列表／A 已发送文本，页内 JS 错误为零；这只验证客户端交错，既非真实 A POST 效果，也不是在线模型。组件 ESLint 最新为 0 error／4 warning；全量 `npm run type-check` 此前退出 2，诊断在其他 12 个文件，不能称全量静态检查通过。这些是隔离 MySQL、TestClient、模拟 API 浏览器、组件四类独立证据，**不构成在线模型、独立 HTTP／生产完整链或 §10 A–D 发布批准**。

**补充一致性检查（同日）：**隔离 MySQL `test_assistant_operator_scenarios_mysql.py` 定向 `3 passed, 69 warnings in 3.61s`，覆盖团队列表边界、相似商机不得证明命令成功／拒绝及精确创建效果一次性授权裁决；进程内 `test_assistant_intake_corrections.py`＋`test_assistant_confirmation_contract.py` 为 `107 passed, 59 warnings in 4.22s`。前者使用隔离身份与 TestClient，后者使用固定结构化输入；均不代表生产运维授权、在线模型日期解析或纯日期到期时刻已获业务批准。

**2026-10-08 U02 独立 HTTP 同链探针未形成证据：**仅在隔离 `127.0.0.1:3308/crm_assistant_acceptance` 创建专用团队 `1992`／用户 `990127464`，并准备了强制核对 DSN、仅加载真实 assistant／teams／auth router（不启动 `app.main` 后台任务）的临时服务。进程监督器的启动、列表和详情均超时；无关的 `/bin/sleep` 健康探针也超时，`127.0.0.1:18267` 无监听，故**没有**创建 A／B 任务、没有专用 Vite 或 Playwright 对真实业务 HTTP 的 A→B→A／迟到 GET／SSE 观察，不能把先前浏览器内模拟 API 的结果升级为该同链证据。随后在限定上述 DSN 的会话中仅清理本轮团队，核验团队、用户、用户-团队关联及该团队助手 task／request／turn／action／CRM effect 数均为零；不涉及共用隔离 MySQL 服务或其他团队。U02 此项仍待实际业务服务和浏览器重跑，§10 A–D 均不批准。

**2026-10-08 U02 监督器复核：**共用 broker 进程 `94343` 存在并持有项目 Unix socket；当天宿主日志 `omp.2026-10-08.1718.log` 有浏览器进程详情请求超时，但没有足以定位 broker 内部根因的堆栈。再次对既有进程执行 `describe` 和对无关 `/bin/sleep` 执行 `start` 均超时；`/tmp` 工作目录的同类启动请求也超时。只读 `netstat -an -f unix` 快照在该 broker socket 路径上显示非零接收队列（2444 字节），说明不能以进程和 socket 存在推断请求已被处理；尚不能据此确定内部阻塞原因。专用 `18267`／`5213` 无监听。本次没有启动业务服务、创建团队或任务，因而没有新增 U02 同链 HTTP／浏览器证据；不重启或终止共用 broker／MySQL，§10 A–D 判定不变。

**2026-10-08 U02 监督器续查（仅阻塞定位，不计验收）：**本轮 `hub ps` 再次返回 `Daemon list request timed out`；`lsof` 证实 broker `94343` 持有项目监听及已连接 socket，其父进程 `1718` 仍在。两次只读 `netstat` 在 broker socket 上观察到 2444、7658 字节接收队列。查阅当前安装的监督器协议实现：客户端的 `request()` 写入带换行的请求，`ping` 本应直接返回项目标识；以该项目现存 broker token 发出**只读 ping** 两次，socket 都已连接且写入返回成功，分别等 2.5／2.2 秒未收到任何响应，随后关闭探针 socket；其间快照另见 135／133 字节接收队列。因而超时至少不只是客户端连不上 socket，尚不能证明 broker 已读取、鉴权或处理这些请求，更不能定位内部根因。对 broker 的 5 秒 macOS `sample` 生成约 4.2 秒／4180 次采样：主线程 2319 次在 CPU，17 个其他线程采样时等待；Bun 原生帧无可用符号，不能据此判定业务回调或内部原因。专用 18267／5213 无监听；未启动进程、创建团队／任务或执行 HTTP／Chromium 探针。不终止、不重启共用 broker／MySQL；§10 A–D 不变。

**2026-10-08 U02 新团队独立 HTTP／Chromium 定向补验（只更新 §9）：**仅在 `mysql+pymysql://root:assistant-test-only@127.0.0.1:3308/crm_assistant_acceptance` 创建全新团队 `1993`／用户 `990127465`；专用 HTTP `127.0.0.1:18267` 同时校验环境与 SQLAlchemy engine 的限定 DSN，只挂载真实 assistant／teams／auth 路由且不启动主应用后台任务；专用 Vite `127.0.0.1:5213` 显式指向该 HTTP 服务。独立认证 HTTP 为 A `ast_9a12b43d14cf4c90bb4d007b151788f6`、B `ast_5b8268dd06264b8cbed218a8d5caebb1` 各创建一条 `ACTIVE/version=0` 任务（POST 201，GET 200）。实际 Chromium `/assistant` 显示 A、B 最近任务；以 CDP 在**响应阶段暂扣真实 GET 200 的浏览器交付**：A→B（B GET 暂扣）→A 后才放 B 响应，当前仍 A、A 输入草稿恢复；反向暂扣 A GET，切 B 后才放 A 响应，当前仍 B、无 A 草稿，再回 A 可见原草稿。中间加载阶段输入框暂为空，不把这一瞬间当成草稿丢失。随后实际浏览器在 A、B 各发送一次文本，经真实服务 `/submit` POST 200；各自响应阶段暂扣 SSE，先切另一个任务再放流，另一个任务的**聊天区**未出现原任务消息或处理进度；B→A 的反向探针还在重开 B 后见 B 自身失败卡。首个 A→B 探针曾把侧栏的 A 标题误判为聊天泄漏，改为检查聊天区后由页面复核；先前 CDP 长调用超时不计通过。独立 HTTP 两任务 GET 都为 `ACTIVE/version=1/error_code=AI_UNAVAILABLE`，各自原 turn GET 200／`FAILED`、事件均为 `[accepted(1),stage(2),error(3,AI_UNAVAILABLE)]`；团队限定 MySQL 查询各有一条所属 turn，任务两条、request 四条、目标 CRM effect 零。新团队没有 AI 配置，因此这些是真实业务 HTTP 的失败轮次与客户端迟到交付时序，**不是在线模型成功、服务端故障或真实网络断流**；既有模拟 API 的 503／签名等待路径与本次证据互不替代。关闭本轮专用 Chromium tab，监督器停止专用 18267／5213；按唯一团队和身份清理后，隔离库 89 张带 `team_id` 的表中该团队均零行，turn events、team、user 均零；删除本轮 JWT 身份文件、临时脚本和数据库备份，不停止共用 MySQL／8000 服务。U02 的真实 HTTP＋浏览器 A→B→A、迟到 GET／SSE 归属为**定向通过**，在线模型签发等待及全套 U01–U06／§10 A–D 发布门禁仍未批准。

### 9.8 2026-10-08 在线模型定向补证（非七项完成／非发布批准）

**适用范围：**本节只补充本次隔离运行态证据，不改写 §9 既有失败记录或 §10 的历史判定。团队 `1994`、用户 `990127466`、角色 `1127`、客户 `4802／星河验收公司`、产品／模块、采购方式及审批流均为 ORM synthetic fixture；模型输入仅为虚构业务事实。专用业务 HTTP 为 `127.0.0.1:18268`，实际 Chromium 页面为 `127.0.0.1:5214/assistant`，数据库实际连接限定为 `127.0.0.1:3308/crm_assistant_acceptance`。没有使用或停止现有 8000 服务，没有修改 .env，没有输出模型密钥、JWT、密码、Authorization 或带密钥配置响应。

**安全证据限制：**后续审阅发现早期 fixture 与 HTTP 包装器直接给进程设置 DATABASE_URL，再核对 engine；HTTP 虽也检查了环境值，但检查发生在赋值之后。因此只能证明实际连接了限定隔离库，**不能证明这些早期入口对错误外部 DSN 失败关闭，不满足该项验收约束**。不靠事后修改临时文件美化历史。最终独立数据库探针和清理入口在导入／连接前检查外部环境，连接后再次核对 engine；清理入口以错误外部 DSN 实测返回 `exit 2 / REFUSED: DATABASE_URL is not the exact allowlisted DSN`。

#### 模型可用性与最小提示词修复

- 原配置模型 `qwen3.5-plus` 两次真实 transport 返回 HTTP 422／model not found；同凭据模型列表 HTTP 200，共 67 项且不含该模型。另有 GLM 回复因 `content_ / extra_forbidden` 被严格 schema 拒绝、gpt-5.5 网关返回要求输入含 json 的 400。这些失败不计业务通过；未增加生产 fallback，也未放宽 schema。
- 本轮成功路径使用隔离团队配置的 `deepseek-v4-pro`，真实 transport／structurer／canonical merge／评分／writer／nominator 均未换固定输出。HTTP 包装器只观测安全字段集合、异常类型和耗时，委托原实现并原样返回／抛出；不等于主应用全部后台任务验收。
- A 在 v5 的真实 StructuredFollowUp transport 成功（6.997 秒），但 `model_fields_set` 缺少 `next_action_absence_reason`；原 `_require_complete_content()` 抛“活动正文结构不完整”，未到 merge。根因为跟进／会议提示词漏列该 canonical 字段。
- 唯一生产源码修复为 `CRM-Server/app/services/assistant/llm.py` 两段提示词：完整列出该字段，要求无事实也返回空值且不得省略，仅记录用户明示暂无的原因／复查条件。typed parsing、完整性校验与独立下一步门禁保持不变。专用服务重启后的同一 A 原文通过结构化／merge／评分并签发下一步 FIELD。会议 C 的真实 StructuredMeeting（16.197 秒）亦完整返回 13 个必需 canonical 字段并通过原校验；这不等于其暂无语义通过。

#### 五条活动的最终持久状态

下表来自清理前独立 READ ONLY 一致快照，按 team＋冻结 submission_id 查得各一条 `ASSISTANT_2` 活动；分数与来源段数不是中间评分历史。

| 任务 | public ID | 最终状态／版本 | 活动 ID | 最终分／来源段 | submission ID |
| --- | --- | --- | --- | --- | --- |
| A | `ast_e33efa9e9146474691397dc443d583c1` | `COMPLETED/v23` | 2408 | 82／2 | `asub_2da819f836684415bad083eb6a1d03d6` |
| B | `ast_4450b97b64194a7b9c8688b42ff7c089` | `COMPLETED/v22` | 2407 | 99／4 | `asub_f4516728809445898a93090ad5e4b1ed` |
| C | `ast_12984e3b8c50441387896b9acd464182` | `COMPLETED/v11` | 2409 | 68／2 | `asub_5d866751f8b144619fa8db5beb512327` |
| D | `ast_2c7647273602415abb9e8246ee042210` | `COMPLETED/v13` | 2410 | 79／2 | `asub_b3bc62efa7e0437db278c0020cf6dde8` |
| E | `ast_e67a47fb9ea74b58a735717873e4469e` | `CANCELLED/v12` | 2411 | 82／2 | `asub_cf32c8d87df0499c9cb422e090e26026` |

- A 活动指纹：`deb49b56d33c63495495afcc7548728e005a78e39abd11bf294977b8dc1de087`。
- B 活动指纹：`d5bebd9d3b8f2c40e4df040a1f3b6ebf693c9b9845490398fbe24819ef233f98`。
- C 活动指纹：`7e0c34c945419f6df85622682caeff2c3851bf8275aadcfb5aafbcc8b3f59c1c`。
- D 活动指纹：`96e488ba4d41f0a7516539febcc9990d6936cdef0dda5d4b871d0248560c2b17`。
- E 活动指纹：`785b3f59d0ede467cd1b8df4af4d11b6e0d2ac0283e1e697a8edf72104296b27`。

- 五条均逐项断言：完整 `content_json`、原始 `source_content`、冻结来源段拼接、最终 `effectiveness_score`、`effectiveness_reason`、完整 `effectiveness_detail_json`、`next_action`、submission ID／指纹及冻结模型元数据与命令一致。title／summary／next_follow_time 等其余映射未在清理前逐项独立断言，**不得把上述范围扩大成所有字段完全相等**。
- 最终团队总数为活动 5、商机 1、目标效果 1；旧 AIJob 0、PostCommitJob 0。command claim 仅 B 有 1 条，A／C／D／E 各 0。任务 ACTIVE 0、turn PENDING／RUNNING 0 后才停止自有 writer 并清理。

#### A／B：实际 Chromium、真实签卡与精确目标效果

- **A 真暂无（U03／D03 定向）：**浏览器初次只输入暂无理由却提交 `choice=null`，及把理由当行动的 79 分稿均不计通过、未写入。先 change-kind 清未提交 canonical，再实际点击“这条没有下一步”，观察选择 banner。请求 `cd3ab73e-f6a1-4f01-a235-5ff7ecbd0299`／turn `atn_e782d28539fb478690fb7e013140cac7` 使用 `awa_7f46189d23914927b64ab15eece734ba / expected_version=16 / choice=EXPLICITLY_NONE`；v20 确认稿 82 分、两段来源，next_action.value=null、canonical next_action 为空、action_evidence=[]，原因精确为“复核结论明确前暂不安排下一步”。最终活动 2408 的 next_action 为 SQL NULL、原因一致。已确认持久成功确认请求 `7c40bb09-735d-41c9-bc64-670c3cc6ffc1`／turn `atn_2afcc18c6fe748d3af6bcd32cb7fb43e`；续验另有一次页面确认点击未保存网络详情，**不能据唯一活动声称 A 只有一次确认 POST**。
- **签名等待下任务隔离（U02／U03 定向）：**A 暂无理由未提交时，将 B 的真实 GET 200 在浏览器接收端交付为 503，页面保留 A、理由及可交互状态；切 B 输入框为空、无 A 理由。B 真实模型处理完成时已切 A，A 聊天与处理进度不串。A 真实选择暂无后 A→B→A 恢复自己的理由与选择 banner。这是客户端接收端故障注入，不是后端真实 503；不替代完整 U01–U06。
- **B 客户与更正（D04 定向）：**首次补充前客户仅为 CANDIDATE、无绑定 authority；模型把联系人“陈明”当客户名，后经真实签名客户 FIELD 回答公司全名继续，不称“丢失已匹配客户”。实际浏览器更正“原审批平均五个工作日改为审批平均三个工作日”，请求 `39f29f53-c8d1-460d-857f-5172fd58e61b`／turn `atn_5817481612694e1b9ea6857a9d9f9767`，使 v10→v14、整稿重评 99 分、四段来源；正文／客户反馈／risks 均为三个工作日，source_corrections 保存 old/new，superseded_source_evidence 保留旧 quote。活动 2407 正文不含旧五个工作日。
- **B 旧卡 409：**浏览器请求 `762e51d1-c5c1-46eb-87bd-d96f55ab169e` 以旧 `awa_15bb975d06d2487c883003f6a18c6ef0 / expected_version=10` 确认，真实返回 `409/STATE_CONFLICT` 附最新 v14；独立快照按该请求键核 AssistantRequest 0 行、关联 AssistantTurn 0 行。新确认签卡为 `awa_bbd9a2157b354d0985d6fc2e6dcd7257 / expected_version=14`。
- **B accepted-only 恢复（U04／U05 定向）：**请求 `75fba6ce-0f06-4605-b3c4-8024b02d36b4` 的真实确认 POST 200 在浏览器接收端只交付 accepted，丢弃后续 SSE；worker／writer／提名器不替换。trace 为一次该确认 POST，随后原 B task GET 200 和内部 `atn_b1c64c0c274d41b9a430c019fa408a1e?after_seq=1` GET 200、多次补读、无第二确认 POST。原确认 turn `atn_de975af20b5e4e36bc8f850e39c37617` 的独立 GET 为 SUCCEEDED，事件 accepted1／stage-write2／stage-write3／waiting4，waiting4.next_turn_id 指向该内部 continue_proposals turn；原 turn 的独立 after_seq=1 只返回 2／3／4。**浏览器实际观察的是原 task→内部 turn 恢复，原确认 turn 游标是独立 HTTP 补证，不能互换叙述**。
- **真实模型提名（O01 定向）：**OpportunityNominations／deepseek-v4-pro transport 4.275 秒；quote 为“陈明明确表示公司计划采购星河采购系统，用于统一采购申请、审批跟踪和预算统计”，segment `seg_8ed9768ff5d41eed`，candidate key `7250fc8d8af54d150cd85a365a8d38a19ce20ffb7d698b0eb0573219c8e9019b`。当时运行态 assembly 注入 OpportunityNominator，传真实 nominations 时禁 legacy hints；不以当前磁盘不同版本推断运行态实现。
- **实际页内商机表单（O04／C 定向）：**浏览器填写“星河采购系统在线验收商机”、成交日 2026-11-30、金额 88000、用户数 12、PERPETUAL、NEW、决策人数 3，选择本团队产品／BASE 模块、采购方式 1055、初始阶段 2696“接触”、owner 990127466。实际截图已核验页内表单和选中值、无可见错误；请求 `aef69474-6dfc-4dc0-a9b5-76bb0519639c`／turn `atn_be32c19f0f76434d8a186f19e1ca6a84` 后 B 为 COMPLETED/v22/SUCCEEDED。此时刷新并显式重开 B，持久显示“活动已写入”“商机已创建”。这是源码变化前的浏览器成功证据。
- **独立 MySQL 精确归因：**唯一商机 `opp_e0335c8543064680b53f786b09f08cbf`（969）、command `acm_22de06c120ed425788d8b884039c3565`、actor 990127466、指纹 `1813dbff0e24df813e32c86c69be6c158dcb3b7d95e2a72330aa5830908013be`，effect 623／opportunity_create、approval 141；claim／商机／效果／助手 receipt 各 1，claim.status=SUCCEEDED、target_invocation=STARTED。effect.stage_snapshot_id 实为 NULL，不将其误判成创建失败；商机 current_stage_snapshot_id=1059，独立 .one() 核同 team／opportunity、stage_name=接触。审批 141 同 team／OPPORTUNITY／business_id=969、PENDING，商机 pending_review。未额外核 snapshot 的 template FK，不能扩大此范围；审批流及后补首节点是 ORM fixture，不是生产审批配置证明。

#### C／D／E：HTTP 边界与明确失败

- C／D 的初始原文经实际浏览器发送；下述后续补充／确认／拒绝受客户端契约阻断后改走**独立真实认证 HTTP**，不是浏览器同链。E 全程为独立真实 HTTP。不得拿这些终态补齐后续 Web 展示验收。
- **C 会议暂无语义未通过：**真模型判 ONLINE_MEETING，主题“档案统一归档需求确认”、内部／客户参会人分组正确，13 个正文必需字段齐全。实际提交 EXPLICITLY_NONE 后 next_action.value=null、确认卡 next_action=null，但 canonical 仍有“客户完成内部档案盘点”的 action_item 和 UNRESOLVED action_evidence。最终活动 2409／68 分只证明字段完整性及真实写入，**不能证明会议暂无语义一致或日期门禁通过**。C 无 offer 是事实，原因未定位，不称已有商机去重通过。
- **D 真实候选后拒绝（O／R 定向）：**活动 2410／79 分先完成写入，再由真实模型提出“陈明明确表示公司计划采购星河报销系统，用于统一发票收集和报销审批”，candidate key `b34536505a4e70a6fc5ae725d4540079821e22a9a1e32e8eb5288b29f808c730`。offer `awa_26932d6308234f0ab80af701d5746a1f / expected_version=11` 实际 POST kind=confirm／choice=reject，turn `atn_f7254988906d4a15a3bba04d7bee3709`，最终 COMPLETED/v13/REFUSED；committed 保留活动并追加 refused:opportunity_create。独立终态快照证实该任务 claim 0、活动仍在，团队唯一商机／效果仍精确归 B，不是 D 产生。
- **E 真实候选后取消（O／R 定向）：**活动 2411／82 分写入后 v11 实际 offer，再 POST kind=cancel，turn `atn_647ca50e1f114f19badf8c52c1470a34`，最终 CANCELLED/v12、无 waiting／processing、committed 保留活动。该任务 claim 0，团队商机／效果仍各 1、归 B。E 构造原文时仅把 D 首处“星河报销系统”替换为“星河费用管理系统”，原文实际含两个产品名；offer 忠于仍存在的报销系统句子，**不据此宣称产品消歧通过，也不归因为模型凭空换产品**。
- **日期缺口保留：**B 虽有带明确日期时间的下一步文本，本次读取 canonical action_evidence 的 due_at 仍 null／resolution_status=UNRESOLVED；没有该行动的真实下游日期任务写入证据。本轮不是 T01／T02 的在线模型日期通过证明，也未覆盖 <60→补充→>=60 的真实阈值跨越。

#### 当前磁盘源码／客户端阻断与定向测试

- 后段观察到客户端 schema／API／聊天组件及服务端相关文件的修改时间均为 2026-10-08 17:23:00 +0800，当时 git status --short 为空；其来源未判定，不恢复／覆盖整批文件。磁盘 llm.py 提示词亦缺本轮修复，故仅重新应用自身两处最小提示词改动。coordinator／proposals 当前磁盘实现与此前专用进程加载版本不同；此后未重启专用 HTTP，不能把其运行态成功冒充当前磁盘源码端到端通过。
- 实际刷新客户端后 GET/tasks 返回 A–D 四条服务端任务，但页面显示“4 条历史任务无法识别，已跳过”“当前没有进行中的任务”。浏览器实际 safeParse：AssistantTaskViewSchema 顶层拒绝 verified_auto_wins、proposals_enabled、processing_turn_id、processing_turn_status、outcome_code、form_errors、error_code；B committed[1] 另拒绝 command_id。**当前客户端契约不兼容是实测阻断，不是四条任务丢失**。E 后来创建，未再刷新核对跳过条数；不编造五条均跳过。
- 当前磁盘源码、限定 DATABASE_URL 下执行 `venv/bin/python -m pytest -q --no-cov tests/unit/test_assistant_model_transport.py tests/unit/test_assistant_intake.py`：`36 passed, 22 warnings in 2.96s`。加 `tests/unit/test_assistant_confirmation_contract.py` 的三文件命令为 `1 failed, 51 passed, 30 warnings in 4.38s`；test_legacy_source_still_tolerates_audit_failure 的 SQLite fixture 未建 crm_customer_legacy_source_progress，旧来源 create 查询该表失败。未改测试／生产代码掩盖此失败。
- 源码变化后原 corrections 测试文件已不存在，原三文件命令退出 4／no tests ran／file not found；未恢复用户移除文件。此前 16＋93 passed 是变化前结果，不作为当前源码证明。本轮未运行前端测试、全套、lint 或 build。提示词 reviewer 无 findings 只覆盖两段提示词及未放宽校验，不批准当前客户端或全部门禁。

#### 隔离清理与门禁结论

- 已停止 model-http-1008、model-vite-1008、model-chrome-1008 并释放本轮 managed tab。未停止共享 MySQL、crm-backend、crm-frontend 或无关 Chromium。
- 清理前 inventory 捕获 89 张 team_id 表、34 turns、39 requests、81 actions、156 条无 team 的 turn events、5 活动、1 商机／效果／阶段快照／审批及其派生记录。数据库没有三张 crm_langgraph_checkpoint* 表：首次 inventory 因缺表拒绝，确认三张均不存在后只按全缺处理、部分存在仍拒绝；没有为清理建表或跳过已有 checkpoint 数据。tenant memory 0，精确 thread 身份捕获 8 条。
- 12 条向量元数据均 PENDING／synced_at null、创建更新时间相同；最初脚本误将 metadata_version=2 判成外部同步异常，查 CustomerEvidenceBuilder.metadata_version=2 后修正，仅此默认版本不构成同步证明。本轮专用服务不加载 main 的向量 scheduler，未运行同步 worker 或手工 upsert；据此提供 no-vector-sync-ran 保证后才清理，**不单凭 PENDING 推断历史无同步**。未连接或修改外部 Qdrant。
- 精确环境／engine 双重校验、FK／跨团队引用检查、child-first、单事务删除 385 行；含团队 1994、用户 990127466、角色 1127、专属关系与无其他引用的两条 fixture permission。提交后另起 verify 及独立 READ ONLY 一致快照：89 张 team 表、捕获无 team 子表、tenant memory、专属身份全部 0；其他团队在 89 张表的逐表行数与清理前相同。该行数比较不等于其他团队正文内容审计。
- 保存本节证据后已精确删除本轮 `/tmp/crmwolf-model-accept-1008.json`、fixture／HTTP／cleanup 三个脚本、cleanup manifest、两张截图与 `crmwolf-model-chrome-1008/` profile；七个文件逐项 exists=false，profile 缺失检查退出 0。未使用宽泛匹配删除其他轮次资源。数据库清理后未重建 fixture、重启专用服务或再次提交确认／拒绝／取消。
- **§10 A–D 全部继续未批准，七项不标完成。**本节补齐真实模型提名／更正／评分／实际表单创建的定向运行态证据，不消除历史副本来源审计、生产老 claim 精确核验、去重阈值／纯日期政策／运维职责批准、灰度监控／生产回滚、完整低分补充与日期用例的缺口；当前客户端不兼容、会议暂无语义及早期入口环境 guard 缺陷也必须保留。后续验收必须针对实际待发布源码重跑，不能混用本次运行态与当前磁盘。
- **阶段性提交决策：**用户确认 Agent 2.0 目前尚无人使用。本次仅将两段提示词修复与本节证据保存为开发阶段提交，不将存量 2.0 任务兼容／迁移作为本次提交的前置条件；该确认不证明旧客户智能历史来源安全，也不代表功能已验收或批准启用。提交前再次运行上述三文件测试，结果为 `1 failed, 51 passed, 30 warnings in 4.51s`，仍为同一 SQLite fixture 缺表失败。当前客户端契约、会议暂无语义及其他缺口保留为启用前待修／待验项。

### 9.9 2026-10-08 当前源码四类修复与隔离同链验收

本节承接 §9.8 暴露的客户端合同、会议暂无、日期执行及商机误去重问题，只覆盖用户批准的四类优化。**不回写历史失败为通过，不宣称七项全量完成，不批准 §10 A–D 发布。**Agent 2.0 尚无人使用，不以不存在的 2.0 存量迁移阻塞本轮；共享 CRM 和旧客户智能的来源安全边界不因此取消。

#### 当前实现合同

- **双端协议与恢复：**`assistant/contracts.py`、`api/assistant.py`、客户端 `schemas/assistant-contracts`、`api/assistant.ts` 与聊天卡片统一封闭的 `activity_write/preview`、`proposal/proposal_kind/candidate` 判别合同及 typed committed receipt；任务种类与七种 CRM 活动种类分开。detail GET 严格校验，列表逐行隔离坏记录并展示跳过数量，不放宽未知命令 schema。`processing_turn_id/status` 暴露本人内部轮次，刷新／重试只补读原轮次，不发第二次输入。任务导航保留 epoch fence，并在当前导航失败时释放无 owner 的 submitting 锁。收据按 committed 判断，不以 COMPLETED 猜活动已写；后续拒绝／取消与此前活动成功分别展示。冻结确认仅执行真实 write，不虚构重新整理／评分阶段。
- **会议明确暂无：**`intake_flow.py`、`coordinator.py` 与 `action_evidence.py` 清除当前 canonical action_items、next_action 和 next_follow_time；旧证据转 `EXPLICITLY_NONE`，原话和原因保留。后续 structurer 即使带回旧行动和旧日期，也不能恢复其下游资格。明确更正只替换唯一匹配旧行动，保留 item_id 并递增证据 revision；普通补充不冒充更正，真实两次行动仍可并存。
- **接受锚点与日期：**模型调用前持久保存 SourceSegment，以 owned AssistantTurn.created_time 固定接受锚点；同 `(turn_id,text)` 幂等，同句新轮保留独立接受事件，类型选择不新增接受记录。日期只绑定本行动局部分句，其他主体、独立句子或后续明确反证不能借旧 ACTIVE 证据授权。真实任务执行器从已存活动重验 canonical、源 segment／引用范围、owner/action、首次 anchor、Asia/Shanghai、parser version、粒度及重算结果，不要求中文原话逐字包含 ISO。活动冻结合同增 `next_follow_time_granularity`，候选顶层增 `due_date_granularity`，后者由持久 validated evidence 绑定、参与候选签名和执行前重验；展示 metadata 不单独授权。纯日期页面仅显示日期，明确午夜 DATETIME 保留时刻，不在浏览器解析中文或凭午夜猜粒度。保留现有活动 09:00 存储及任务日末 23:59:59 政策，二者不混用；证据本身仍是 DATE＋00:00。
- **商机目标与真实归因：**`opportunity_target_matching.py` 在 pre-offer 和 executor 共同按同团队／客户、产品、模块集合、采购类型、许可类型／订阅期限比较目标；金额、人数、成交日期不是目标身份。商机名 strip 后完全相等，不以 SQL 原始名称前筛漏掉 padded 旧名，不加 fuzzy 阈值；明确重复跳过、不同目标继续、歧义保守不创建。`proposals.py`／`crm_proposal_commands.py` 的 command_id/fingerprint 与 claim、目标 API 的 assistant_command 及精确 checked_effect 对齐；首次成功和恢复都不再按同名对象或任意阶段变化猜成功，无归因旧 claim 保 UNKNOWN 且不重放。未扩张 auto_won 语义。

#### 验收层级与数据库身份

- 本轮**未调用真实模型**。独立 HTTP harness 使用固定 classifier／structurer／quality gate、受控接受时钟，真实认证路由、durable worker、RealActivityWriter 和 RealCRMProposalExecutor；仅输入虚构业务数据。SQLite 回归、TestClient、mock API 组件测试与下面的独立 HTTP／浏览器／MySQL 证据分别计量，不能拿固定输出当真实模型能力。两个 bounded 只读审查已完成；其确认的问题分别由日期授权和导航失败回归先红后绿修复，不以审查意见代替运行验证。
- 独占 `--rm`、无 volume 的 `crmwolf-fouropt-1008c` MySQL 8.0 容器，仅 `mysql+pymysql/root@127.0.0.1:3308/crm_assistant_acceptance`；导入应用前校验外部 DSN identity，导入后精确比较 engine.url，不覆盖错误入口环境。当前 schema 由 `Base.metadata.create_all()` 建立，是 **ORM fixture，不是迁移验收**。`001_initial` 为依赖外部 init_db 的 no-op marker；未对已存在全 schema 盲跑 `alembic upgrade head`，也不声称待发布副本迁移通过。
- 新建团队 `10082026`、用户 `100820261`、客户 `cus_four_1008c`。HTTP `18313`、Vite `5213`、专属 CDP Chromium `18314`；Vite 只代理本轮 HTTP。未重建已清理团队 1994、未访问共享业务库、未修改 .env、未调用 8000 业务服务、未运行模型／向量后台或连接外部 Qdrant。

#### 独立 HTTP、真实页面和独立 MySQL 同链结果

| 场景 | 当前源码实测证据 |
| --- | --- |
| 跨夜补充＋DATETIME | `ast_6557581974904467aa5a588e48914f18`：首句接受 `2026-10-08T23:59:00`，FIELD 补充 `2026-10-10T08:00:00`；冻结活动和真实下游任务完成。独立 MySQL 逐字段断言 1 活动、1 FollowUpTask、1 CREATED Event；due_at=`2026-10-14T15:00:00`、DATETIME、Asia/Shanghai，证据 anchor 仍是首次接受、segment=`seg_faa116c5d9a6620746c1`、quote=`我下周三下午三点发方案`、parser=`assistant-date-v1`，源接受轮次和两条 source_records 均对应。confirm 事件只有 write start/done，没有 structure／quality_gate；确认不增加固定 seam 调用计数。刷新重开 COMPLETED 任务，实际页面可见“活动已写入”。 |
| 类型选择不重锚定 | `ast_8d07265ca8464f6a879adeb61e87ada6`：初始 UNCLEAR，经真实签发 action/version 选择 FOLLOW_UP，选择前后 source_records 全量相等、未追加接受事件，得到 typed 活动确认；未确认业务写，随后正常取消。 |
| 会议明确暂无＋旧模型值 | `ast_4adae97c4a6e407e9ca00f9be6e29427`：先有 ACTIVE 行动和日期，FIELD 接受 EXPLICITLY_NONE 与等待预算审批原因，固定 structurer 故意返回旧值。frozen action_items=[]、next_action/next_follow_time=null、无 ACTIVE evidence；真实确认后独立 MySQL 1 活动、0 Task/Event，原“暂无下一步”保留，旧证据为 EXPLICITLY_NONE。确认前后 structure/gate 均为 5。相同请求键同 input 重放 200，旧 action 换新键 409，独立复查仍无重复写。 |
| 纯日期完整链 | `ast_5906289ac9a44a448e967f03a7ba7043`：实际 `/assistant` 点击确认活动，再确认创建跟进任务，两个卡片均显示 `2026-10-14`，无默认 09:00／证据午夜伪时刻；独立 MySQL 1 活动、1 FollowUpTask、1 CREATED Event，任务 due_at=`2026-10-14T23:59:59`、DATE、Asia/Shanghai。证据仍为 `2026-10-14T00:00:00`、quote=`我下周三发方案`、anchor=`2026-10-08T23:59:00`、parser=`assistant-date-v1`；活动仍沿既有规则存 09:00，未改变业务存储政策。两次确认均未增加 structure/gate。旧展示合同的自有纯日期任务通过正常 cancel 收口，未改其已写活动、持久卡或指纹。 |
| 同一内部轮次刷新与恢复 | 上述纯日期任务写活动后受控 hold `continue_proposals`，真实 GET 见 `atn_be3fc72e216d409789a03dcd90e08e48/RUNNING`、无 waiting、活动 receipt 已持久。单次局部 request 监听内 reload，只观察 assistant latest-active GET 和该 **同一 turn GET**，零 assistant POST；textarea 禁用、可见“活动已写入”、“重试同步”启用。实际点击恢复又只 GET 同 turn；release 后再补读得到 typed 日期 proposal 并继续写真实任务。DOM、截图及点击均验证，不把空 request 数组当零 POST 证据。 |
| 实际页面拒绝后续 | `ast_f37b8dd8d8c443fd8ba2a1558f16ad18`：页面点击写活动、proposal“暂不处理”，显示拒绝而非 FailureCard，GET 终态 COMPLETED、committed 保留活动并追加 refused:follow_up_task_create；GET 同步终态后实际可见“已完成”“活动已写入”。独立 MySQL 1 活动、0 Task/Event。 |
| 实际页面取消后续 | `ast_dc1d882837354a0baddf852e1a631a37`：活动写入且 proposal 待确认时点击“取消任务”，页面显示“已取消”和“活动已写入”，提案仅历史记录、无失败卡；GET CANCELLED、waiting=null、committed 仅原活动。独立 MySQL 1 活动、0 Task/Event，活动未回滚。 |

#### 最后改动后的集中验证

- 后端 13 文件：`test_assistant_action_evidence`、`intake`、`confirmation_contract`、`proposals`、`opportunity_target_matching`、`opportunity_targets_adapter`、`api`、`coordinator`、`stage_events`、`runtime_isolation`、`task_state`、`quality`、`events`；批准 DSN 下 guarded pytest `-q --no-cov`：**226 passed，57 warnings，29.90s，exit 0**。覆盖日期局部绑定／后续撤销、更正、跨夜真实 writer／executor、暂无 canonical、签名／幂等／归因、目标歧义、团队边界等实际行为，不等于 MySQL 并发或生产事故演练。
- 客户端 7 文件：`assistantContracts.spec.ts`、`SalesAssistantProcessing`、`SalesAssistantChat`、`SalesAssistantReplay`、`SalesAssistantVisibility`、`MeetingConfirmationCard`、`AssistantTaskSidebar`；Vitest **69 passed，exit 0**。日期精度回归先红（服务端缺 next_follow_time_granularity、页面泄露 T09:00:00）再绿；DATETIME midnight 保留。恢复／拒绝测试另断言用户可见活动收据，不仅检查传给侧栏的 props。
- 18 个相关后端源／测试文件完整 Ruff：**All checks passed**；恢复合理的中文 grammar／提示和 FastAPI Depends 例外，Pydantic 运行时类型不盲移 TYPE_CHECKING，未放宽配置。7 个相关前端生产文件 scoped ESLint `--max-warnings=0`：exit 0。将 tests/ 纳入同一 ESLint 命令的尝试因现有 tsconfig.json 仅 include src/ 而出现 7 个 parser project 错误；未改项目配置绕过，不称测试文件 ESLint 已过。
- `npm run type-check`：**exit 2，9 个无关文件 22 diagnostics**，与本轮前已有结果相同，本轮助手生产文件无诊断。涉及 SettingsProductsPage.test.ts、ListAdvancedTools.vue、PaymentPlanFormDialog.test.ts、SettingsApprovalFlowsPage.vue、DataTable.vue、ProcurementStagesSettings.vue、SettingsContent.vue、SettingsMembersPage.vue、SettingsProcurementMethodsPage.vue；未扩张修复。`npx vite build`：**exit 0，5212 modules transformed**，仅为资产构建；不能称包含 vue-tsc 的 `npm run build` 通过。

#### 剩余发布边界

本轮修复及运行证据限以上四类当前源码。未验实际待发布副本的 Alembic 升级、MySQL 并发／进程死亡、线上商机候选生产者→页内表单→真实创建整链、生产历史来源／老 claim 盘点、灰度监控与生产回滚；adapter 的 DISTINCT sentinel 只到真实 API 边界，不是 MySQL 实际商机创建。没有重试不存在的 qwen3.5-plus、没有模型 fallback，也不把 §9.8 的历史真实模型／表单运行态升级成本轮证明。§10 A–D 继续未批准；本轮不提交、不推送、不部署。

#### 本轮自有资源清理

- 已释放 `four-opt-1008c-owned` 浏览器 tab；旧 `four-opt-1008c-ui` 已不存在，未释放其他 tab。关闭本轮 HTTP client，停止 `assistant-fouropt-http-1008c`、`assistant-fouropt-vite-1008c`、`assistant-fouropt-chrome-1008c`、`assistant-fouropt-db-1008c`；监督状态均为 exited。`docker container inspect crmwolf-fouropt-1008c` 返回 No such container，确认本轮无 volume 的自毁容器及隔离 fixture 已移除。
- 按精确清单移除本轮 token、Chrome profile、harness／guard／inspector 脚本、Vite 配置、五份 owned task DB JSON 和三张截图；清单含可能未生成的 preview 路径，共 19 个路径逐项核验均不存在，不把原已缺失路径计为实际删除文件。未使用宽泛匹配删除旧轮次文件；未停止或修改 8000、共享 MySQL、团队服务或无关 Chromium。证据保存在本节及对应源码行为回归，不为复查重建 fixture。


### 9.10 2026-10-09 A 批次迁移图与隔离迁移阻断（未批准）

本次先核对当前 checkout 的迁移图，再建立全新、无 volume 的临时 MySQL；**没有把空库结果或合成 fixture 解释为历史存量安全证据**。

- **当前迁移图：**当前 checkout 的 `CRM-Server/migrations/versions/` 源文件最新为 `150_profile_version_attestation.py`；`cd CRM-Server && venv/bin/alembic heads` 返回 `150_profile_version_attestation (head)`。`151_assistant_proposal_policy` 只存在于历史运行态的未跟踪提交 `05cf9f0b`，不在当前 HEAD `88f0c3eb`／其 `d49d8dad` 基线的源迁移目录中；当前未凭文档补写 151，也未把历史运行态的 `alembic current` 结果混入当前 checkout 证据。
- **隔离迁移 smoke：**新建无 volume 容器 `crmwolf-a-migration-1009`，仅绑定 `127.0.0.1:3310`，数据库为专用 `crm_a_migration`，未连接共享 `crm-mysql-dev`。空库 `alembic current` 无已应用 revision；`alembic upgrade head` 先执行 `001_initial`，随后在 `002_user_roles_team` 因 `001_initial` 是 no-op、目标表 `user_roles` 尚未建立而失败。失败后隔离库仅保留 `alembic_version=001_initial` 和 1 张表（迁移版本表）。这证明当前基线不能从空库直接重放完整 schema；不是历史副本迁移通过证据。没有使用 `Base.metadata.create_all()`、`alembic stamp head` 或手工 SQL 绕过失败。
- **迁移静态编译补充：**使用当前 `env.py` 的 MySQL offline 模式生成 `upgrade head --sql` 时，输出 `001_initial` 后在 `002_user_roles_team` 的 `op.alter_column('user_roles', 'team_id', nullable=False)` 处失败：MySQL 方言要求 `existing_type`，但该迁移未提供。此为离线 SQL 生成阻断，不能替代历史副本在线升级结果；真实空库在线 smoke 仍先因 `user_roles` 不存在而失败。
- **后段静态编译补充：**从 `147_assistant_crm_effects` 生成至 `head` 时，`148` 可生成 DDL／bootstrap SQL，但 `149_assistant_command_operator` 在 offline `MockConnection` 上调用 `sa.inspect(connection)`，导致离线生成失败；从 `149` 到 `150` 单独生成成功，输出两列新增、唯一索引替换及版本更新 SQL。该结果只说明这段 SQL 可渲染，不证明在线历史副本执行成功。
- **更早迁移的离线边界：**从 `002` 继续静态生成会在 `003_config_tables_team` 的 `conn.execute(...).fetchall()` 处失败；该迁移依赖在线数据库结果并包含数据变更。因此当前迁移链不能通过一条完整 offline SQL 生成命令完成端到端校验，仍必须等待获准历史副本做在线、可回滚的实际迁移验收。
- **迁移图结构盘点：**通过 `ScriptDirectory` 加载当前迁移目录，得到 153 个 revision；`base=001_initial`、唯一 `head=150_profile_version_attestation`，无重复 revision ID、无缺失 parent。图中存在两个分支点（`123_payment_record_idempotency`、`135_deal_journey_public_ids`）和两个 merge revision（`125_merge_activity_and_payment_heads`、`137_datatable_export_permissions`）。因此 revision 图本身闭合，但这不证明任一历史 schema 能安全在线升级。
- **在线依赖静态盘点：**对 153 个迁移源码做 AST 只读扫描，发现 16 个迁移文件共 28 处 `sa.inspect`／`inspect` schema inspection 调用，63 个迁移文件共 205 处 `fetchall`、`fetchone`、`scalar`、`scalars`、`first` 或 `all` 结果消费调用。该盘点支持“offline `--sql` 不是完整验收方法”的边界判断；不将静态命中数解释为在线失败，也未修改迁移源码。
- **现有历史审计器覆盖边界：**`scripts/audit_legacy_profile_versions.py` 当前只遍历 profile versions 与 current pointers，解析六段正文、直接 `CustomerActivity` 的 Assistant 2.0 文本命中和 citation resolver 结果；没有调用 `trace_customer_source_provenance()`，也没有聚合旅程／业务流事件、事实及事实来源、承诺、任务及任务事件、删除墓碑、向量文档、来源进度完整性或全量来源水位。该结果与当前设计一致：在用户批准审计扩展前，不修改脚本、不以现有聚合结果宣称 A 通过。
 - **历史副本状态（§9.10 记录时点）：**当时仓库、已知临时资源和部署制品中仍没有带完整历史业务数据、`alembic_version`、生成来源和可验证 SHA-256 的获准待发布副本；共享 `crm-mysql-dev` 仍明确排除。后续建立的当前 dev 存量隔离副本及其审计证据见 §9.11，仍不等同于正式待发布副本。
- **当前源码定向回归：**A 相关单元测试命令为 `81 passed, 23 warnings`，退出码 0，覆盖审计器、来源认证、投影合同、citation resolver、水位、投影图和读时 readiness gate。将来源 MySQL 集成测试指向本次 3310 隔离库时，测试的严格 DSN guard 要求专用 `3308/crm_assistant_acceptance`，因此结果为 `23 skipped`；没有写入该迁移 smoke 库，也不把 skipped 记为 S01–S09 通过。
 - **门禁结论（§9.10 记录时点）：**当时仅完成迁移图核对、空库失败复现和无历史数据的源码回归；后续历史 dev 存量隔离审计见 §9.11，但仍未完成历史副本迁移和真实待发布副本上的 S01–S09。因此 A 继续**未批准**，A–D 不得发布、灰度或扩大流量。下一硬前置仍是取得获准的带历史数据待发布副本；不补写 151，不以空库零异常或 synthetic fixture 关闭 A。

### 9.11 2026-10-09 真实 dev 存量隔离副本全链路审计（仍未批准）

本节补充并更新 §9.10 的时间点记录：从共享开发库生成一致性逻辑副本后，仅在新建隔离容器上恢复并审计；共享 `crm-mysql-dev` 未执行迁移、DDL、测试写入或清理。本节副本是**当前 dev 存量副本**，不是正式待发布副本，不能替代获准发布前验收。

- **副本与迁移边界：**压缩 dump 大小为 `532885741` bytes，`gzip -t` 通过，SHA-256 为 `8407a6a92d744820265dc4907d87cbb8d6bf3839cf003bea7eb2d85e4c1eb74f`；恢复至隔离容器 `crmwolf-a-devclone-1009`、宿主 `127.0.0.1:3311`、数据库 `crm_a_devclone`。副本 `alembic_version` 为 `151_assistant_proposal_policy`；当前 checkout 源码 head 为 `150_profile_version_attestation`，因此 `alembic current` 与 `alembic upgrade head` 均在 revision lookup 阶段报 `Can't locate revision identified by '151_assistant_proposal_policy'`，未执行迁移。未补写 151、未 stamp、未手工修改版本表、未 downgrade 或以 SQL 绕过。
- **只读与 schema 兼容：**全链路审计在临时 SELECT-only 身份、MySQL `REPEATABLE READ`、`START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY` 单次快照中完成，输出仅为聚合值和固定错误码。当前 ORM 与历史 schema 唯一差异为 `crm_customers.license_authorized_users` 缺失；使用 `load_only()` 排除该列，88 个客户加载成功，88 个强上下文及完整来源水位构建成功；未执行 DDL 或修改源码。
- **存量规模：**客户 `88`，profile versions `2440`，current pointers `88`，source progress `88`，vector documents `1385`，activities `480`，activity deletion tombstones `0`。
- **来源链聚合：**客户级 provenance `VERIFIED=45`、`UNKNOWN=43`；活动来源 `FORM=283`、`AGENT=181`、`CUTOVER_MIGRATION=4`、`ASSISTANT_2=12`，2.0 活动按规则排除；journey events `VERIFIED=441`；commitments `VERIFIED=399`；tasks `VERIFIED=317`、`UNKNOWN=23`；task events `VERIFIED=441`、`UNKNOWN=9`；facts `VERIFIED=359`、`UNKNOWN=307`；fact source rows 缺失 `0`；tombstones `0`。
- **历史正文与引用：**六段正文来源未证明 `2440`；Assistant 2.0 直接正文命中 `0`；profile versions blocking `2440`、uncertified `2439`；citations available `86759`、unavailable `22287`；current pointer 非法 `0`。这组直接命中结果不能证明不存在转述或已删除来源污染。
- **水位与 current：**不完整五项 source watermark `2439`；版本 source snapshot mismatch `2439`；current watermark mismatch `87`；current snapshot mismatch `86`；source progress policy 均为 `LEGACY_PROFILE_ELIGIBLE_V1`，provenance status `VERIFIED=1`、`UNVERIFIED=87`。因此水位／进度不能作为历史正文可发表证明。
- **向量文档：**来源类型为 `business_flow=234`、`follow_up=426`、`follow_up_task=326`、`sales_commitment=399`；来源状态 `VERIFIED=1364`、`EXCLUDED=12`、`UNKNOWN=9`；sync status `SYNCED=1385`。未输出 vector text、title、document key、source ID 或业务标识。
- **shadow diff：**在同一只读快照内从强上下文生成 deterministic draft，六段 canonical JSON 机械比较为 changed `86`、unchanged `1`、无 current version `1`；因历史正文未证明、来源或认证门禁不满足，安全语义下 blocked `88`，shadow errors `0`。`unchanged=1` 不解释为安全或可发表。
- **S01–S09：**严格测试副本恢复曾因 `crm_langgraph_checkpoint_writes` 表空间耗尽（OS error 28）失败并已清理；此前指向非批准端口的运行被 strict DSN guard 记为 `23 skipped`，没有任何 S01–S09 pass 证据。故 S01–S09 仍未执行，不能以 skipped 或失败副本关闭 A。
- **门禁结论：**本节完成的是当前 dev 存量副本的只读审计与 shadow diff，不是迁移通过、正式待发布副本验收或 S01–S09 通过。A 继续**未批准**；A–D 不得发布、灰度或扩大流量。

### 9.12 2026-10-10 客户档案移除对七项的前置变更（与 §1 头部声明配套）

本节记录档案撤下在本 TRD 范围内的实际执行结果，作为 §1 作废声明与 §10 A 批次改判的证据基础。

- **数据库（共享 dev `crm-mysql-dev`@3307 实测）：**Alembic 链修复为 `…150 → 151_customer_license_authorized_users → 151_assistant_proposal_policy → 152_remove_customer_profile_prepare → 153_remove_customer_profile_complete`，`alembic_version=153`。九类非 `alias` 事实 548 条全删（来源/修订为 0），`alias` 18 条保留；三张档案表（projection_versions/current/legacy_source_progress）information_schema 确认不存在；向量仅存 `business_flow=241/follow_up=426/follow_up_task=326/sales_commitment=399`，`DELETE_PENDING=0`；客户记忆仅 `retrieval` 区段。未对生产执行。
- **行为层（合并后 main 测试实测）：**事实类型收窄为 alias-only（`ensure_allowed_customer_fact_type` 拒绝九类，`CUSTOMER_FACT_TYPE_REMOVED`）；九类事实提案在 `validate_candidate` 前置拒绝；问答上下文 `customer_facts` 恒空、不再查 legacy progress；客户记忆仅收四个证据字段的结构化 retrieval 引用；客户智能 Graph 事实提炼/评估/持久化节点移出执行图；旧 `/profile` 路由统一 `410 CUSTOMER_PROFILE_REMOVED`（含 refresh POST）；三个档案调度器不再注册；`advance_eligible_progress` 等死调用从全部 CRUD 清除，`legacy_profile_source` 仅存 origin/provenance 判定。合并后 272 项相关测试通过（§9.9 十三文件 225 项 + 撤下专项 47 项）。
- **对七项的影响判定：**①来源/投影/水位——验收对象已不存在，A 批次档案侧条件关闭（唯一保留边界：2.0 来源不流入客户智能读取，由上述行为层改动+回归覆盖）；②③④⑤⑥⑦的目标与验收行不受影响，B/C/D 门禁条件不变。§9.8 曾记录的“SQLite fixture 缺 `crm_customer_legacy_source_progress` 表”类测试阻塞随表删除一并消失。
- **遗留声明：**开发库 Qdrant 中对应 152 标记点的实际删除未经退役服务执行验证（MySQL 侧已清零）；生产发布时必须先跑 `customer_profile_vector_retirement_service.retire_pending_documents` 确认点消失再执行 153。本节不构成 B/C/D 门禁的任何通过证明。
## 10. 实施批次、发布门禁、兼容与待决策

| 批次 | 完成门禁与回退边界 |
| --- | --- |
| A · 来源与读安全 | **2026-10-10 更新：**旧客户档案能力已整体移除（§1 头部声明），原“发表栅栏/存量版本盘点/S01–S09”验收对象不复存在，A 批次的档案侧条件**全部关闭**。仍需维持的只有：2.0 来源不流入客户智能读取的回归测试保持绿色；Alembic 152/153 已在目标环境执行。 |
| B · 命令真实归因与状态 | 创建／阶段目标**实际提交**写唯一相关效果，分段赢单单独记录；CLAIMED 超租约和人工权限上线。C01–C06、R01–R04、T03 的 MySQL 双会话、丢响应和恢复通过；不能先部署靠同名猜成功的创建交互。旧历史 claim 保留不明状态。 |
| C · 候选／表单／语义 | 真实候选来源、已有商机静默去重、Agent 内表单、有效 canonical 更正／日期依据、最终评分和下一步门禁上线；O01–O07、D01–D04、T01–T02 通过，旧入口规则不变。 |
| D · 前端与灰度 | 判别 payload 双端一致、409／error／内部 turn 补读、切任务隔离、typed 呈现；U01–U06 用实际浏览器走通，功能按团队渐进开启。指标和回滚 T04 通过后扩大流量。 |

### 9.13 2026-10-10 收口批次：TRD 对齐、WIP 入库、T03 运维权限、商机提名链（仍在 B/C/D 门禁内）

本节记录当日收口四项的实际执行与证据；**不改变 §10 B–D 未批准结论，不构成灰度或发布批准。**

- **TRD 对齐：**§1 头部新增批次作废声明，§10 A 批次改判“档案侧条件全部关闭”，待决策 1 划掉，§9.12 记录档案移除实测（Alembic 153、九类事实 548 清零、三表删除、向量四类留存、272 项回归）。提交 `7dd53ee1`。
- **WIP 入库：**§9.9 四类修复的前端 14 文件单独提交 `50dcdb4e`；后端部分已随 `3fed3dfe` 先行入库（含 action_evidence、opportunity_target_matching 及 13 个测试文件），当日验证 225 项通过。顺带发现并修复 manifest 与后端 `list_query` 算子目录脱节（`d49d8dad` 曾把 enum 算子从 8 削到 4），按后端 `DEFAULT_OPS` 对齐 3 个字段，提交 `eea71544`。
- **T03 运维权限（§7.1 首段落地）：**`GET /v1/assistant/unknown-commands` 从“团队全量、del current_user”改为三层：持 `assistant:commands:reconcile:team`（迁移 149 已种子）看本团队 UNKNOWN+CLAIMED（含 `last_checked_at` 最小字段）；普通团队成员仅看本人记录（owner 过滤）；无团队归属 403。`list_unresolved_command_claims` 增加 `owner_user_id`/`include_claimed` 参数。TDD 四用例（本人隔离、越权 403、operator 看团队含 CLAIMED、跨团队不泄漏）先红后绿，提交含于 `feat(assistant): enforce owner and operator claim query scopes`。
- **商机提名链（§2.2 第 1 步的模型侧）：**`opportunity_nominator.py` 恢复并适配当前 `source_records` segment 结构：模型只提名 `opportunity_create/opportunity_stage` 信号（结构化 schema、闭世界 prompt、无金额字段、阶段必须带 target+相邻阶段），服务端 `validate_candidate` 独立重绑证据与 CRM 权威；接入 `offer_next_proposal`（规则 hints 优先，模型提名兜底）；模型/凭据不可用时记 warning 并降级为不提名，绝不阻塞已提交活动。提名器 3 用例（引用转发、阶段缺目标丢弃、无信号空返回）通过；5 个旧 fixture 缺 `crm_ai_config` 的回归由降级路径覆盖后全绿。
- **集中回归：**助手 15 文件 232 passed；档案撤下专项 10 文件 58 passed；前端助手 7 文件 69 passed；T03 operator 端到端见下方补证。剩余人工裁决端点（§7.1 后半，依赖决策 3）与 §10 决策 2/3/4 业务批准；B/C/D 门禁维持未批准。


**T03 隔离 MySQL + 独立 HTTP 端到端（2026-10-10 补证）：**一次性 `--rm` 容器 `crmwolf-t03-1010`（仅 127.0.0.1:3308/crm_t03_acceptance，MySQL 8.0），`Base.metadata.create_all()` ORM fixture（非迁移验收）；种真实 `Permission(assistant:commands:reconcile:team)`+`Role(ASSISTANT_COMMAND_OPERATOR)`+`UserRole` 权限行、4 用户（owner/peer 同团队、operator 持角色、outsider 仅属团队 2）、5 条 claim（owner UNKNOWN、peer UNKNOWN+CLAIMED+RECONCILED、跨团队 UNKNOWN）。独立 Uvicorn 18260 + 独立 HTTP 实测：owner 200 仅 `t_owner_u/UNKNOWN`；peer（无权限成员）200 仅 `t_peer_u/UNKNOWN`、不见本人 CLAIMED；operator 200 全团队 `t_owner_u+t_peer_u/UNKNOWN、t_peer_c/CLAIMED`、无 RECONCILED；outsider 200 仅本团队 `t_foreign`，零跨团队泄漏。无成员对他人记录有任何可见性。首启小表集曾被启动任务缺 `crm_agent_turn_executions` 拖垮，重建完整 schema 后通过——不构成对部分表环境的兼容承诺。服务与容器已清理（`docker rm -f` 后 0 残留）。
**本轮门禁复核（截至 2026-10-04；A–D 均不批准发布／扩大流量）：**下表的“未批准”不否定上面指定测试通过，而是逐项遵守该批次完整条件；隔离库内无记录不代表生产无存量。下一次判定必须附对应实际环境、身份和事务证据，不能把固定候选、TestClient、mock API 或故障注入升级成真实模型／生产事故证据。

| 批次 | 本轮实测及尚缺的发布证据 | 判定 |
| --- | --- | --- |
| A | 隔离 MySQL S01–S09、多会话栅栏、旧投影 TestClient 已覆盖定向样本；`alembic current` 曾报 `150_profile_version_attestation (head)`。此前只读盘点版本 0、current 2、非空版本指针 0；2026-10-03 新的只读一致快照 CLI 在指定隔离库运行退出 0，版本仍为 0、current 16、无效指针 0、不可用引用 0；SQLite 定向污染／跨团队测试 `2 passed`，不能把没有历史版本的隔离库视为历史安全证明。旧来源进度此前 3 行均 `LEGACY_PROFILE_ELIGIBLE_V1/UNVERIFIED`、eligible revision 4–6、删除 revision 合计 0。尚缺生产或待发布副本按团队／版本迁移水位、真实历史正文来源及引用全量审计、旧／新正文差异、隔离／重建证据；签名及现存原文直接命中不能证明无转述或已删除来源污染。 | **未批准**：S 行局部验证，真实存量盘点门槛缺失。 |
| B | 隔离 MySQL 精确 target effect、实际目标 commit、提交前／后第二笔赢单故障注入、丢响应只读核对、双会话、SIGKILL、授权人工核对有定向通过；H 独立隔离服务＋独立 HTTP 客户端已取得非空 `UNKNOWN` owner／授权 team 200、未授权及跨团队 403、无精确效果 409、目标独立事务写精确回执后正确证据 200 与重复 409，独立会话见一商机／效果／助手收据及审计；claim 来自隔离构造，不是生产未知事故。C05 的新增探针在第二次外层 commit 后抛连接异常，新 session 证实赢单效果、一次结算且零阶段重放；O07 新增 `settle_proposal()` 调真实阶段执行器的提交前／后故障组合，证明阶段 `UNKNOWN` 或精确回执 `RECONCILED` 与已拒绝的创建、已写活动互不回滚，均非独立 HTTP。2026-10-03 新 H 探针补上由独立 HTTP 签名表单调用实际 `settle_proposal()`、自有服务进程在 `NOT_STARTED` claim 提交后／目标事务返回后分别 SIGKILL，独立会话在崩溃前后核对零效果拒绝／精确效果只读补单、扫描两次 `[1,0]`、目标写入不重放；两次 fixture 均已清理。此为受控隔离进程死亡，不是实际停电或生产流量；老存量 claim 不能凭相似目标结算。须补生产老 claim 只读核对、部署后监控及实际模型／业务故障全链，任何无效果 `STARTED` 保 `UNKNOWN`。 | **未批准**：目标回执及隔离 HTTP 故障恢复有定向证明，不等于整批完成。 |
| C | O、D、T 定向 MySQL／单元覆盖 quote、有效表单、更正、时区及去重；O02 部分名称歧义先复现误签再保守拒绝，独立探针又证实“分析平台”会误拦不同目标“分析平台培训服务”，业务阈值未批准。O04 隔离 MySQL＋TestClient 验证实际目标写一次、同键重放／冲突、有效跨身份 404；独立 Uvicorn 8020＋HTTP 重现签卡 task GET 200、POST accepted→waiting SSE、turn GET SUCCEEDED、同键补读不重复写、改金额或旧 action 新键 409，以及有效跨团队／同团队其他用户各自 GET task／turn、POST submit 均 404、零外部写。此前 Chromium 5189 填固定 form 并 POST 200；那次浏览器 DOM 回执与先前独立 fixture 的 MySQL 不能混称同链。2026-10-03 专用 5191 Chromium **同一隔离任务**从固定来源 offer→页内 form→POST 200→活动及商机 DOM 回执，独立 task GET `COMPLETED/SUCCEEDED`、隔离 MySQL 唯一商机及 `opportunity_create` 精确效果与该任务匹配；另有浏览器旧卡 409 更新为服务端草稿／错误后修正成功、拒绝保留活动且不建第二商机。O07 独立阶段由真实执行器受控注入提交前失败／提交后响应丢失，分别保留 `UNKNOWN`／精确核对成功，原创建拒绝与活动不回滚。上述 offer 仍来自持久固定候选／canonical 活动及 `_candidate_hints()` 规则；隔离团队真实模型 turn 为 `AI_UNAVAILABLE`，**未证明模型候选／评分→offer→form→CRM 的全链**。日粒度到期策略、目标不唯一及高置信去重阈值未审定。 | **未批准**：同链浏览器与目标效果已在固定候选隔离路径验证；真实候选及业务边界缺证。 |
| D | 九个前端助手 Vitest 文件定向 `104 passed`，含 mock API 的 U01–U06；独立 HTTP 有持久 turn／事件游标、签名表单 waiting SSE、task／turn GET。先前 Chromium 5189 的固定 form POST 200、另一独立 fixture 的 DOM 回执不能并称同链。2026-10-03 专用 5191 Chromium 同任务观察固定 offer→页内 form→POST 200→完成及活动／商机回执，并由独立 GET／MySQL 核同一创建效果；两任务浏览器交错时 A 未提交草稿不串入 B；独立 HTTP 使 B 重签后，浏览器旧卡实际 POST 409，使用服务端最新错误草稿修正提交；浏览器拒绝、取消后仍显示此前已写活动。A 的受控**客户端接收端**只收 `accepted` 后丢流，观察一次 POST、GET 原 task／turn `after_seq=1`、无第二 POST、最终回执；刷新后从最近任务重开已完成 A 可读回执。前序浏览器也观察终结 `AI_UNAVAILABLE` 后的一次 POST 补读，但不代表已提交活动或未知结果。2026-10-04 新增同链隔离验收：团队 `990129393` 的固定草稿签卡由 Chromium 5193 点击、请求指向显式 18242 隔离服务，任务 `ast_93ddb4b637e74fd3b75b60bb5a74b628` 只有一次浏览器确认 POST；独立 task／turn GET 与 MySQL **先证明**内部 `continue_proposals` turn `atn_0d6e9ba319814b7e86120e9653688fe2` 为 `RUNNING`、唯一活动 `990130111`，然后刷新 `/assistant`；浏览器只发同任务／turn GET、游标 `after_seq=0→1`，无重发 POST；独立 GET 仍为 `RUNNING` 且一活动。释放受控暂停后该 turn `SUCCEEDED`、同 task 出现固定规则候选的提案 wait，活动仍唯一；浏览器显示历史活动回执与填写商机入口。浏览器请求清单未捕获响应回调，200 和隔离头由独立 GET／页内 fetch 核对，不声称逐条浏览器响应都已抓取。该场景是**隔离 fixture＋受控暂停**，不能称为真实模型、网络故障或生产证据。T04 新增专用团队 `990129394` 的**独立服务进程**双开 PID `81521`→双关 PID `87364`→双开 PID `7496` 验收，真实认证 HTTP 保留旧版 v1、停发新 offer／旧发表、恢复后只发表旧合格 v2 并重新签发固定候选；发表／切换健康检查仅为 `/tmp` 控制入口，非生产 API。进一步双开 PID `30104` 预签商机卡、双关 PID `32763` 完整提交：真实认证 HTTP 200，独立 MySQL 核 **关闭后仍创建一商机及一精确效果**；开关只阻止后续签发，**不撤销已有签卡**。未验证真实模型链、按团队渐进开启、监控指标或生产回滚；当前签卡执行边界不满足“关闭即停新商机”。 | **未批准**：隔离独立重启已验，但旧签卡可在关闭后执行 CRM 写入；团队灰度、观测和真实模型／生产回滚门禁仍未过。 |

**2026-10-05 门禁接续复核（承接 §9.7 已记录的 2026-10-04 验收；非新的生产验收）：**上表 D 行末的“关闭后仍创建商机”是**此前只有进程级开关**时，已签发旧卡仍可执行的历史探针结果，不应当作后来团队持久回滚栅栏的当前结论。后续专用团队／独立服务重启、认证 HTTP、Chromium 及隔离 MySQL 同链验证：停用使旧代次卡退役，旧 action 返回 409，原任务零命令 claim、零 CRM 效果；恢复也不自动复活旧卡，须显式重查并签发 generation 5 新卡，旧 action 仍 409。另设探针的 `STARTED` 命令只凭精确目标回执结算；无回执仍为 `UNKNOWN`，探针的一商机／一效果不能归于原任务。本日仅只读执行指定隔离库 `alembic current`，显示 `151_assistant_proposal_policy (head)`；这不代表生产迁移已执行。上表 A 行所述 `150_profile_version_attestation` 是此前观察值。尚缺生产／待发布副本历史来源与 claim 盘点、真实模型链、按团队灰度监控及生产回滚证据，且 O02 去重阈值等业务决策未获批准；故 **A–D 全部继续未批准发布或扩大流量**。

兼容原则：新写仅用新 schema 和目标相关命令；历史已完成活动仍一次性最终化、不重评分、不改业务评分历史；未完成的**已签发活动确认**按 §5 迁移新签名等待且保留冻结命令；未 claim 的旧提案退役旧签名并重新核证，已 claim／结果不明的旧提案保持待人工核对、绝不重放；历史已完成任务／旧拒绝回执仅读时适配，不破坏动作审计；旧档案不可变版本不篡改。迁移、唯一索引和历史回填必须是 Alembic 与可重跑任务，记录按 team 的数量／策略版本／高水位，不在仓库根目录放一次性脚本或报告。新旧前端交错发布期间服务端明确 wire 版本：未升级的客户端不得看到可提交的新提案卡；不能靠放宽前端 schema 让不认识的命令可点。


**审阅需明确的决策（未批准前不得声称现行能力）：**
1. ~~旧档案共享旅程非事件聚合字段的独立合格来源与污染正文处置~~——**2026-10-10 随档案移除作废**，无存量正文需要处置。
2. 日期只有日粒度时的业务到期时刻（本草案沿用现有任务纯日期 23:59:59，而不是跟进时间 09:00）、对“周末／月底左右”等表达的歧义边界；确认后冻结解析版本与基准。
3. 独立运维权限名及谁可在团队内人工核对，含需要何种**目标提交证据**才能关闭老格式 `UNKNOWN`；无证据不允许直接改 `SUCCEEDED`。
4. 现有商机高置信去重的业务判定阈值及目标不唯一时是呈现选择卡还是不提建议；任何选择都不得靠同名读回证明命令成功。

**完成定义：**只有七项的相应验收行在**实际改造后的**服务、MySQL 并发／崩溃、旧投影读取和 Web 页面上取得可复核证据，并在文档记录结果，才可把对应批次标为完成。本 TRD 的创建本身不构成任何业务修复或测试通过。
