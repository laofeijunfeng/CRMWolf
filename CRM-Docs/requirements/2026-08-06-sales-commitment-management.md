# 销售承诺管理系统需求与技术方案

## 1. 背景

当前 CRM 已经以客户跟进记录为销售工作中心。销售在跟进记录中沉淀沟通内容、下一步动作和下次跟进时间，Agent 也已经具备从自然语言中整理跟进内容、识别下一步动作和时间的能力。

随着客户数量增加，只依赖销售逐个打开客户详情查看下一步动作，会导致跟进遗漏。传统任务管理可以解决提醒问题，但会引入额外操作：销售既要写跟进记录，又要维护任务完成状态，容易变成新的负担。

本方案目标是建设一个“销售承诺管理系统”：系统从跟进记录和业务上下文中抽取未来承诺和下一步动作，自动维护可查询、可追问、可总结的工作安排。用户仍然围绕跟进记录和 Agent 自然对话工作，而不是被迫使用一个僵硬的任务页面。

## 2. 产品定位

销售承诺管理系统不是传统待办清单，而是 CRM 对销售沟通中“未来应发生事项”的结构化理解层。

它回答的问题包括：

- 今天我的任务有哪些？
- 本周我的任务有哪些？
- 下周我有什么工作安排？
- 我还有哪些任务没完成？
- 我还有哪些客户要跟进？
- 哪些客户已经逾期没有跟进？
- 本周我完成了什么内容？
- 上次说要确认预算的客户有哪些？
- 哪些客户卡在预算、采购、试用反馈或合同推进上？

系统应尽量避免要求用户手动创建任务、勾选完成任务或进入独立任务页面。任务的生成、关闭、延期、取消和追问应主要由跟进记录、Agent 语义理解和明确用户反馈驱动。

## 3. 核心原则

1. 跟进记录仍然是用户主工作流

   用户只需要继续记录客户跟进。系统从跟进记录中抽取下一步动作、时间和承诺，不要求销售额外维护任务。

2. 结构化表是事实源

   今日、本周、逾期、完成状态等确定性查询必须来自 MySQL 结构化数据。LLM 和向量数据库只能辅助抽取、匹配、解释和总结，不能成为唯一事实源。

3. 向量数据库用于语义证据

   Qdrant 用于检索跟进记录、承诺、任务、客户背景、商机进展等语义证据，帮助 Agent 做自然语言查询、语义关联和上下文补全。

4. Agent 是交互入口

   第一阶段不强制新增任务页面。Agent 需要提供自然语言查询、追问、延期、取消、补充进展、工作总结等能力。

5. 低置信不自动变更关键状态

   LLM 可以判断一条新跟进是否完成旧任务，但必须输出置信度、证据和原因。低置信、高价值或可能误关任务的场景必须进入用户确认。

6. 不复用 Agent 会话任务作为业务任务

   现有 `crm_agent_tasks` 是 Agent 会话、等待确认和工具审计状态，不应作为销售业务任务表。销售承诺和跟进任务需要独立业务表。

7. 不以短期实现牺牲模型边界

   分阶段实施只表示控制行为范围，不表示把关键状态塞进不合适的表、绕过审计或省略幂等。任务事实、投影运行、任务事件、向量证据和 Agent 会话状态应各自有清晰职责，避免后续自动流转、历史回填、重试和多 Agent 协作时形成历史债。

## 4. 概念模型

### 4.1 Commitment 销售承诺

Commitment 表示从客户沟通中抽取出来的未来事项。

典型类型：

- 我方承诺：销售承诺给客户发报价、发资料、安排演示。
- 客户承诺：客户承诺反馈预算、确认试用结果、内部评审。
- 双方约定：双方约好下次会议、演示、拜访。
- 风险等待：客户正在审批、采购、预算、试用等环节，需要销售在某个时间点追问。

Commitment 更接近“语义事实”，它描述销售对话中的未来约定。

### 4.2 Follow-up Task 跟进任务

Follow-up Task 是从 Commitment 中派生出来的销售可执行动作。

示例：

- 周三回访王总确认预算。
- 下周五跟进试用反馈。
- 明天发送报价方案。
- 月底前确认客户采购流程进度。

任务是 Agent 查询和提醒的主要结构化对象，但用户不需要手动维护任务。

### 4.3 Work Summary 工作结果

Work Summary 用于回答“我本周完成了什么”。

它不能只看已完成任务，还需要综合：

- 本周关闭的跟进任务。
- 本周新增的客户跟进记录。
- 本周推进的商机阶段。
- 本周新增或更新的合同、回款、发票、License 等业务对象。
- Agent 对工作内容的归纳总结。

## 5. 用户体验

### 5.1 记录跟进时自动生成下一步动作

用户输入：

```text
今天和越秀金融王总电话沟通了试用情况，客户整体反馈不错，但是还要等内部预算确认，下周三再问一下预算有没有批。
```

Agent 创建跟进记录后，系统自动抽取：

- Commitment：客户需确认预算。
- Follow-up Task：下周三回访王总确认预算。
- due_at：下周三。
- source_activity_id：本次跟进记录。

用户无需再创建任务。

### 5.2 新跟进自动关闭旧任务

旧任务：

```text
周三确认越秀金融预算是否批复。
```

用户新增跟进：

```text
今天问了王总，预算已经批了 20 万，客户准备走采购流程，周五我再确认采购方式。
```

系统判断新跟进与旧任务语义相关，并自动：

- 将旧任务标记为 `COMPLETED_BY_ACTIVITY`。
- 记录 `closed_by_activity_id`。
- 生成新任务：周五确认采购方式。

### 5.3 新跟进与旧任务无关时追问

旧任务：

```text
确认越秀金融预算。
```

新跟进：

```text
今天和客户技术同事沟通了部署服务器配置。
```

系统判断新跟进没有覆盖预算任务，且旧任务已到期或即将到期。Agent 在跟进记录创建后追问：

```text
已记录这次部署沟通。上次你安排了“确认预算”，这次记录里没有看到相关进展。这个任务要继续保留、延期，还是取消？
```

用户可以自然回复：

- 先放着。
- 下周五再说。
- 已经确认了，预算 20 万。
- 不用管了。
- 今天问了，还没结果，下周三再问。

Agent 根据语义解析结果执行延期、完成、取消、补充跟进记录或生成下一任务。

### 5.4 自然语言查询

用户问：

```text
今天我的任务有哪些？
```

Agent 查询结构化任务表，结合向量证据补充上下文，回答：

```text
今天有 5 个客户需要跟进，其中 2 个已逾期。建议优先处理：
1. 越秀金融：逾期 2 天，需确认预算是否批复。上次王总说内部本周评审。
2. 光大证券：今天需确认试用反馈。上次客户提到性能测试还有疑问。
3. ...
```

用户问：

```text
本周我完成了什么？
```

Agent 查询本周已关闭任务、跟进记录和业务推进事件，输出工作总结，而不是只列任务完成清单。

### 5.5 页面手工录入活动的触发规则

用户不通过 Agent，而是在客户详情页面手工添加活动时，也应该进入同一套销售承诺/任务投影流程。

原因是：任务来源不是“Agent 对话”，而是“客户活动记录”。只要最终客户活动中存在明确的 `next_action` 或 `next_follow_time`，不论它来自页面填写、Agent 创建、AI 整理抽取、线索迁移，都应被统一处理。

建议规则：

1. 页面手工填写了 `next_action` 和 `next_follow_time`

   活动保存后可以立即生成确定性跟进任务；AI 整理完成后再执行一次幂等投影，必要时补充承诺证据或修正标题。

2. 页面只填写了 `next_follow_time`，没有填写 `next_action`

   可以生成低置信跟进任务，默认动作类似“跟进客户进展”；如果 AI 整理后从原文抽取出更明确的下一步动作，则更新任务标题和 action_text。

3. 页面只填写了 `next_action`，没有填写 `next_follow_time`

   建议生成 commitment，不生成强待办；如果 AI 整理从原文中解析出时间，再生成开放任务。这里不是实现取舍，而是产品语义：没有明确时间的事项更像“待观察承诺”，不应进入今天/本周这类强时效任务列表。

4. 页面没有填写 `next_action` 和 `next_follow_time`

   不应仅因为创建了活动就生成任务。应等待 AI 整理结果：如果整理后仍然没有下一步动作和时间，则 projection no-op，只记录“无可投影任务”即可。

5. 页面原文包含下一步动作但用户没有拆字段填写

   现有客户活动 AI 整理会尝试从 `source_content` 中抽取 `next_action`，并在没有用户明确填写下次跟进时间时，从原文时间表达解析 `next_follow_time`。因此任务投影必须监听“AI 整理完成后的活动字段”，不能只看活动刚创建时的字段。

### 5.6 Agent 录入活动的触发规则

Agent 录入跟进记录时，本质上也是调用客户活动创建接口，只是 Agent 会提前从用户自然语言中解析出 `next_action` 和 `next_follow_time` 并传入接口。

建议：

- Agent 创建活动后不要单独维护一套任务逻辑。
- Agent 只负责创建客户活动和解析原始字段。
- 后续任务生成、承诺抽取、历史幂等、权限归属都交给统一的 FollowUpTaskProjectionService。
- 这样页面录入、Agent 录入、AI 创建客户时附带的跟进记录、线索迁移记录都能共享同一套规则。

### 5.7 客户活动更新和删除的触发规则

任务既然从客户活动投影而来，就必须处理客户活动后续被编辑、清空下一步字段或删除的情况，否则会出现“跟进记录已经改了，但任务还停留在旧安排”的体验问题。

建议规则：

1. 用户修改 `next_action` 或 `next_follow_time`

   触发 `ACTIVITY_UPDATED` 投影。系统优先更新同一 `source_activity_id` 产生的开放任务，而不是新建重复任务。更新应写入任务事件，保留旧标题、旧动作、旧时间和新值。

2. 用户清空 `next_action` 和 `next_follow_time`

   如果该活动曾生成开放任务，系统应将同源开放任务标记为 `CANCELLED` 或 `SUPERSEDED`，`resolution_reason` 记录为 `SOURCE_NEXT_STEP_REMOVED`，并写入事件和投影运行记录。不能继续保留一个已经没有来源依据的开放任务。

3. 用户删除或作废客户活动

   不建议物理删除已生成的任务和事件。应根据活动删除语义将同源开放任务标记为 `CANCELLED`，`resolution_reason` 记录为 `SOURCE_ACTIVITY_DELETED`，保留审计链路。如果任务已经完成，则不回滚完成结果，只补充来源活动已删除的审计信息。

4. AI 整理修正活动字段

   AI 整理后的最终字段仍然走同一 `ACTIVITY_STRUCTURED_COMPLETED` 投影入口。若 AI 将原先模糊的下一步动作解析得更清楚，更新已有任务；若 AI 判断原文没有下一步事项，则不生成任务，或取消同源的低置信任务。

5. 活动更新后的幂等原则

   同一活动更新不能简单依赖新 `task_hash` 创建新任务。投影服务需要先按 `team_id + source_type + source_activity_id + owner_id` 查找同源开放任务，再决定更新、取消、跳过或新建，避免同一条活动因多次编辑产生多个开放任务。

## 6. 数据模型建议

### 6.1 crm_sales_commitments

用于保存从跟进记录中抽取的未来承诺。

建议字段：

| 字段 | 说明 |
|------|------|
| id | 主键 |
| public_id | 对外承诺 ID，建议使用前缀如 `scm_`；Agent tool、前端接口和外部通讯使用该字段，不暴露数据库主键 |
| team_id | 团队 ID |
| customer_id | 客户 ID |
| owner_id | 承诺/任务归属用户，来自来源跟进记录的 `owner_id`；历史活动没有 owner 时由 `creator_id` 回填 |
| creator_id | 记录创建人；自动抽取时可使用触发来源活动的 `creator_id` 或系统 Agent 用户，需在 `evidence_json` 标明创建来源 |
| source_type | 来源类型，第一版为 `CUSTOMER_ACTIVITY` |
| source_activity_id | 来源客户活动 ID |
| commitment_type | `OUR_COMMITMENT` / `CUSTOMER_COMMITMENT` / `MUTUAL_AGREEMENT` / `RISK_WAITING` |
| actor | `USER` / `CUSTOMER` / `BOTH` / `UNKNOWN` |
| title | 承诺标题 |
| detail | 承诺详情 |
| due_at | 承诺预期发生时间 |
| due_at_text | 原始时间表达 |
| due_at_granularity | 时间粒度：`DATE` / `DATETIME` / `WEEK` / `MONTH` / `UNKNOWN`，用于区分“下周三”和“下周内”等表达 |
| due_at_timezone | 解析时间使用的时区，默认取用户或团队时区 |
| status | `OPEN` / `FULFILLED` / `SUPERSEDED` / `CANCELLED` |
| confidence | 抽取置信度 |
| extraction_model | 抽取使用的模型 |
| evidence_json | 来源证据、字段和解释 |
| created_time | 创建时间 |
| updated_time | 更新时间 |
| closed_time | 关闭时间 |

### 6.2 crm_follow_up_tasks

用于保存 Agent 可查询、可解释的销售跟进任务。

建议字段：

| 字段 | 说明 |
|------|------|
| id | 主键 |
| public_id | 对外任务 ID，建议使用前缀如 `fut_`；Agent tool、前端接口和外部通讯使用该字段，不暴露数据库主键 |
| team_id | 团队 ID |
| customer_id | 客户 ID |
| owner_id | 任务归属用户，继承来源跟进记录 `owner_id`；历史活动没有 owner 时由 `creator_id` 回填 |
| creator_id | 任务记录创建人；自动投影时通常等同于来源活动 `creator_id`，但必须与 owner_id 分离，支持代记录、未来领导指派、Agent 代创建、任务转派等场景 |
| commitment_id | 对应承诺 ID，可为空以兼容未来其他来源 |
| source_type | `CUSTOMER_ACTIVITY` / future source |
| source_activity_id | 生成该任务的活动 ID |
| closed_by_activity_id | 自动完成该任务的活动 ID |
| task_type | 第一版为 `CUSTOMER_FOLLOW_UP` |
| title | 任务标题 |
| action_text | 下一步动作 |
| due_at | 到期时间 |
| due_at_text | 原始时间表达 |
| due_at_granularity | 时间粒度：`DATE` / `DATETIME` / `WEEK` / `MONTH` / `UNKNOWN` |
| due_at_timezone | 解析时间使用的时区，默认取用户或团队时区 |
| status | `OPEN` / `COMPLETED_BY_ACTIVITY` / `SNOOZED` / `CANCELLED` / `WAITING_CONFIRMATION` / `SUPERSEDED` / `HISTORICAL_CLOSED` |
| priority | `LOW` / `MEDIUM` / `HIGH` |
| confidence | 生成置信度 |
| match_confidence | 被后续跟进关闭时的匹配置信度 |
| resolution_reason | 完成、延期、取消或等待确认的原因 |
| evidence_json | 来源证据、匹配依据、LLM 判断摘要 |
| created_time | 创建时间 |
| updated_time | 更新时间 |
| closed_time | 关闭时间 |

`DUE` 和 `OVERDUE` 不建议作为持久状态，优先通过 `due_at` 和当前日期动态计算。

### 6.3 crm_follow_up_task_events

用于审计任务状态变化。

建议事件：

- `CREATED`
- `UPDATED`
- `AUTO_COMPLETED`
- `SNOOZED`
- `CANCELLED`
- `SUPERSEDED`
- `WAITING_CONFIRMATION`
- `CONFIRMED_BY_USER`
- `REOPENED`
- `HISTORICAL_CLOSED`

事件字段至少包括：

- public_id
- task_id
- team_id
- actor_user_id
- event_type
- from_status
- to_status
- source_activity_id
- payload_json
- created_time

### 6.4 标识、外部通讯和审计字段约定

任务和承诺都属于业务实体，建议第一版即补充 `public_id` 和 `creator_id`。

`public_id` 规则：

- 数据库内部关联使用自增主键 `id`，例如 `crm_follow_up_tasks.commitment_id` 指向 `crm_sales_commitments.id`。
- API、Agent tool、前端路由、LLM 上下文、向量证据元数据和日志中使用 `public_id`。
- Agent 入参不接收数据库主键，避免模型或外部调用方拿到内部 ID 后形成不稳定依赖。
- tool 层需要做 public_id 到内部 id 的解析，并在解析后继续执行 team、客户访问和任务 owner 权限校验。
- `public_id` 使用有语义的前缀，便于日志排查和 Agent 识别实体类型，例如承诺 `scm_xxx`，跟进任务 `fut_xxx`，任务事件 `fte_xxx`。

`creator_id` 规则：

- `owner_id` 表示这件事归谁负责。
- `creator_id` 表示这条任务或承诺记录是谁创建的。
- Phase 1 给客户活动补充独立 `owner_id`。自动生成任务时，任务/承诺 `owner_id` 来自来源活动 `owner_id`，`creator_id` 来自来源活动 `creator_id`。
- 历史客户活动没有 `owner_id` 时，迁移或回填阶段使用活动 `creator_id` 初始化 `owner_id`，作为历史数据兼容策略。
- 如果后续支持领导通过 Agent 给销售指派任务，`creator_id` 是领导，`owner_id` 是销售。
- 如果后续支持 Agent 批量整理历史任务，`creator_id` 可以是系统 Agent 用户或触发该操作的用户，具体来源写入 `evidence_json` 和事件表。
- 权限判断不能只看 `creator_id`；用户是否能查询客户、是否能操作任务、是否是任务 owner，需要分开判断。

事件表说明：

- `crm_follow_up_task_events` 主要服务审计和状态追踪，默认通过 `task_public_id` 查询任务事件流。
- 管理端、Agent 或外部 API 需要单独引用某条事件时，使用 event `public_id`，不要暴露数据库主键。
- 自动状态迁移事件需要在 `payload_json.rollback` 中保留恢复快照；自动完成/取消至少能重开任务，自动延期至少能恢复 previous due_at。

### 6.5 约束和索引建议

第一版需要把幂等、查询性能和权限过滤提前固化到数据库层。

建议唯一约束：

- `crm_sales_commitments.public_id` 全局唯一。
- `crm_follow_up_tasks.public_id` 全局唯一。
- `crm_sales_commitments`: `team_id + source_type + source_activity_id + commitment_hash` 唯一，避免同一跟进记录重复抽取同一承诺。
- `crm_follow_up_tasks`: `team_id + source_type + source_activity_id + task_hash` 唯一，避免重复生成任务。

建议索引：

- `crm_follow_up_tasks(team_id, owner_id, status, due_at)`：支撑“我的今天/本周/逾期任务”。
- `crm_follow_up_tasks(team_id, customer_id, owner_id, status, due_at)`：支撑同客户、同 owner 的自动关闭候选。
- `crm_follow_up_tasks(team_id, customer_id, status)`：支撑“这个客户还有哪些任务”。
- `crm_sales_commitments(team_id, customer_id, owner_id, status, due_at)`：支撑客户承诺和等待事项查询。
- `crm_follow_up_task_events(team_id, task_id, created_time)`：支撑任务详情和审计时间线。
- `crm_follow_up_task_projection_runs(team_id, source_type, source_activity_id, trigger_type, created_time)`：支撑按活动排查投影运行。
- `crm_follow_up_task_projection_runs(team_id, status, created_time)`：支撑失败重试和运维看板。

实现说明：

- `commitment_hash` 和 `task_hash` 不需要暴露给 API，可由标准化后的 title、action_text、due_at、source_activity_id 等字段生成。
- 历史回填和活动后处理必须使用同一套 service 写入，不能分别实现两套幂等逻辑。
- 如果 MySQL 版本或迁移策略不适合直接建长文本 hash 唯一键，应保存定长 hash 字段。

### 6.6 来源实体 public_id 处理

任务和承诺自身第一版必须有 `public_id`。来源实体也需要区分处理：

- `Customer`、`Opportunity` 等已有 public_id 的实体，Agent 和 API 继续使用 public_id。
- 当前 `CustomerActivity` 仍以数字 id 对外返回，第一版任务表内部可以继续保存 `source_activity_id` 数据库主键。
- Agent tool 输出来源活动时，不应把 `source_activity_id` 直接暴露为可调用标识；可以只展示来源摘要、发生时间、客户 public_id，或返回只读展示字段。
- 如果后续需要 Agent 精确引用、打开、补充或修正某条跟进记录，建议给 `crm_customer_activities` 补充 `public_id`，例如 `act_xxx`，再将 tool 入参切换为 activity public_id。
- 这不阻塞第一版任务查询和自动生成，但属于进入第二阶段前建议处理的技术债。

### 6.7 向量证据

现有 `CustomerVectorDocument` 已经支持客户活动、客户画像、客户概况和成交旅程事件等证据。新增承诺和任务后，建议增加新的 source type：

- `sales_commitment`
- `follow_up_task`

向量证据元数据契约：

| 字段 | 说明 |
|------|------|
| source_type | `sales_commitment` 或 `follow_up_task`；原有客户活动继续使用 `follow_up`，不混用 |
| source_object_id | 新增承诺/任务统一使用实体 `public_id`，例如 `scm_xxx`、`fut_xxx` |
| business_object_type | `sales_commitment` 或 `follow_up_task` |
| business_object_id | 与业务实体 `public_id` 一致，用于 Agent 命中向量证据后回 MySQL 校验最新状态 |
| metadata_json.customer_public_id | 客户对外 ID；保留 `customer_id` 仅作为内部同步和过滤字段 |
| metadata_json.owner_id | 任务/承诺归属人，继承跟进记录 owner，不继承客户 owner |
| metadata_json.status | 写入索引时的状态快照；回答任务状态必须回 MySQL 校验，不以该字段作为事实源 |
| metadata_json.due_at / due_at_text / due_at_granularity / due_at_timezone | 到期时间语义和结构化时间快照 |
| metadata_json.source_public_id | 来源对象已有 public_id 时保存；客户活动当前没有 public_id 时不写 synthetic id |
| metadata_json.evidence | 只保留 quote、reason、terms 等语义证据，过滤 `activity_id`、`task_id` 等内部数据库主键 |

索引文本示例：

```text
客户：越秀金融
承诺类型：客户承诺
事项：客户下周三反馈预算审批结果
来源：2026-08-06 跟进记录
状态：OPEN
```

向量库只保存可检索证据和可回表的 public_id，不作为任务状态事实源。Agent 回答“今天任务”“未完成任务”“是否完成”等确定性问题时，必须先查结构化任务表；向量命中只能补充上下文、相似事项、语义引用和解释依据。

### 6.8 客户活动任务投影运行表

为了排查“为什么某条跟进记录没有生成任务”，不建议把任务投影状态字段直接加到 `crm_customer_activities`。客户活动表应保持“跟进记录本身”的领域职责；任务投影是一个后处理 pipeline，存在多触发、多重试、多版本输入和历史回填，不适合用活动表上的单组状态字段承载。

建议新增独立投影运行表：`crm_follow_up_task_projection_runs`。

建议字段：

| 字段 | 说明 |
|------|------|
| id | 主键 |
| public_id | 对外排查 ID，可选；如果管理端或 Agent 需要引用某次投影运行，则使用前缀如 `tpr_` |
| team_id | 团队 ID |
| source_type | 来源类型，例如 `CUSTOMER_ACTIVITY` |
| source_activity_id | 来源客户活动数据库主键 |
| trigger_type | `ACTIVITY_CREATED_DETERMINISTIC` / `ACTIVITY_STRUCTURED_COMPLETED` / `ACTIVITY_UPDATED` / `HISTORICAL_BACKFILL` |
| status | `PENDING` / `RUNNING` / `COMPLETED` / `SKIPPED` / `FAILED` |
| skip_reason | 跳过原因，例如 `NO_NEXT_STEP` / `NO_DUE_AT` / `LOW_CONFIDENCE` / `DUPLICATE` / `SUPERSEDED_INPUT` |
| error_message | 失败摘要，避免写入过长堆栈；详细异常进入日志 |
| attempt_count | 当前投影运行重试次数 |
| input_snapshot_hash | 本次投影读取的活动关键字段 hash，用于判断旧运行是否基于过期输入 |
| projection_hash | 标准化后的投影结果 hash，用于幂等和排查重复 |
| commitment_count | 本次创建或更新的承诺数量 |
| task_count | 本次创建或更新的任务数量 |
| created_task_ids | 可选 JSON，保存本次新建任务 public_id 列表或内部 id 列表；对外展示时必须转换为 public_id |
| updated_task_ids | 可选 JSON，保存本次更新任务 public_id 列表或内部 id 列表；对外展示时必须转换为 public_id |
| started_at | 开始处理时间 |
| finished_at | 结束处理时间 |
| created_time | 创建时间 |
| updated_time | 更新时间 |

状态含义：

- `COMPLETED`：已成功完成投影，可能创建、更新或确认无需变更。
- `SKIPPED`：活动已处理，但根据最终字段没有可生成任务的下一步信息，或本次输入已被更新的投影运行覆盖。
- `FAILED`：投影执行异常，需要重试或人工排查。

独立投影运行表的价值：

- 客户活动表不被后处理 pipeline 状态污染，活动仍然只表达客户沟通事实。
- 同一活动可以保留多次运行记录：保存后确定性投影、AI 整理后最终投影、用户更新后投影、历史回填投影。
- 不会出现“最新一次状态覆盖前一次失败原因”的问题，便于排查为什么某次没有生成任务。
- 可以独立做重试、失败告警、幂等判断和回填审计。
- 后续增加 LangGraph 节点、LLM 抽取版本、向量写入状态时，不需要持续扩张客户活动表字段。

### 6.9 时间、时区和日期粒度

任务查询高度依赖时间口径，必须在第一版明确，否则 Agent 回答“今天”“本周”“逾期”会出现边界不一致。

建议规则：

- `due_at` 按系统现有 datetime 存储规范保存；如果系统统一保存 UTC，则投影服务负责把用户自然语言时间按用户或团队时区解析后转换为 UTC。
- `due_at_timezone` 保存解析时使用的时区，默认取当前用户时区；如果系统暂未维护用户时区，则取团队时区。
- `due_at_granularity` 保存时间粒度。用户说“下周三”是 `DATE`，说“下周三下午 3 点”是 `DATETIME`，说“下周内”是 `WEEK`。
- Agent 查询“今天”“本周”“下周”时，必须先按当前用户或团队时区计算确定时间范围，再查询 MySQL。
- `OVERDUE` 不持久化为状态，而是按 `due_at`、`due_at_granularity`、当前时间和查询时区动态计算。
- 对只有日期没有具体时间的任务，展示时应按日期展示，不强行显示 00:00；内部可使用团队工作日默认时间作为排序辅助，但不能让用户误以为约定了具体时刻。

### 6.10 客户活动 owner_id

Phase 1 同步给 `crm_customer_activities` 补充独立 `owner_id`，用于表达这条跟进记录对应的工作归属人。

字段语义：

| 字段 | 说明 |
|------|------|
| owner_id | 跟进记录对应的工作归属人，任务和承诺 owner 从该字段派生 |
| creator_id | 跟进记录创建人，表示谁录入了这条记录 |

规则：

- 页面用户自己添加活动时，默认 `owner_id = current_user.id`，`creator_id = current_user.id`。
- Agent 代表当前用户记录活动时，默认 `owner_id = current_user.id`，`creator_id = current_user.id`；如果未来 Agent 支持代记录或指派，必须显式传入 owner。
- 历史客户活动迁移时，使用 `creator_id` 初始化 `owner_id`。
- 任务和承诺投影必须读取活动 `owner_id`，不能再直接假设活动 `creator_id` 就是任务 owner。
- 客户 `owner_id` 仍然只表示客户负责人，不作为任务默认归属来源。

## 7. 服务层设计

### 7.1 CommitmentExtractionService

职责：

- 从客户活动中抽取未来承诺。
- 解析下一步动作、责任方、时间表达和置信度。
- 输出结构化结果，不直接落最终任务状态。

输入：

- customer activity
- customer strong context
- recent activities
- current date/time

输出：

```json
{
  "commitments": [
    {
      "commitment_type": "CUSTOMER_COMMITMENT",
      "actor": "CUSTOMER",
      "title": "确认预算是否批复",
      "detail": "王总预计下周三反馈内部预算审批结果",
      "due_at_text": "下周三",
      "due_at": "2026-08-12T09:00:00",
      "confidence": 0.91,
      "evidence": ["客户说下周三反馈预算"]
    }
  ]
}
```

### 7.2 FollowUpTaskProjectionService

职责：

- 基于客户活动的 `next_action` / `next_follow_time` 和抽取出的 commitment 生成跟进任务。
- 为无 commitment 但有明确 `next_action` / `next_follow_time` 的活动生成任务。
- 对没有 `next_action` 且没有 `next_follow_time` 的活动执行 no-op，不生成任务。
- 防止重复生成同一任务。
- 维护 source_activity_id、commitment_id 和 owner_id，其中 owner_id 必须来自来源跟进记录的归属人，不能默认使用客户负责人。
- 支持同一活动被多次触发投影：活动创建后、AI 整理完成后、用户更新活动后，都通过幂等 key 更新或跳过。
- 处理同源活动更新、清空下一步字段和活动删除：更新同源开放任务、取消失去来源依据的开放任务，并写入事件和投影运行记录。

触发来源：

- `ACTIVITY_CREATED_DETERMINISTIC`：活动刚保存后，基于用户或 Agent 已显式填写的字段做保存后确定性投影。
- `ACTIVITY_STRUCTURED_COMPLETED`：客户活动 AI 整理完成后，基于最终 `next_action` / `next_follow_time` 做最终投影或修正。
- `ACTIVITY_UPDATED`：用户更新原文、下一步动作或下次跟进时间后重新投影。
- `ACTIVITY_DELETED`：用户删除或作废客户活动后，取消同源开放任务并保留审计。
- `HISTORICAL_BACKFILL`：历史回填复用同一 service。

Phase 1 设计边界：

- 若活动保存时已经有用户明确填写的 `next_action` 或 `next_follow_time`，可以立即投影，保证 AI 整理失败时也不漏掉用户明确安排。
- AI 整理完成后必须再次投影，使用幂等逻辑更新标题、动作、时间和 evidence，而不是重复创建任务。
- 若活动保存时没有任何下一步字段，则不立即生成任务；等待 AI 整理完成后再判断是否需要生成。

### 7.3 TaskReconciliationService

职责：

- 在新客户活动创建或更新后，检查该客户未完成任务。
- 判断新活动是否完成、推进、延期、取消或无关。
- 根据置信度决定自动流转或进入 Agent 追问。

候选任务过滤优先使用结构化条件：

- 同 team_id
- 同 customer_id
- 默认同 owner_id
- status 为 `OPEN` 或 `WAITING_CONFIRMATION`
- due_at 在合理窗口内，例如过去 90 天到未来 30 天

之后再使用向量检索和 LLM rerank 判断语义关联。

默认只在同客户、同任务归属人的开放任务中做自动关闭或自动延期，避免售前的一次跟进误关闭销售自己的任务，或销售的跟进误关闭售前承诺。跨 owner 的任务流转只在新跟进记录中明确出现“我已经替某某确认了预算”“售前演示已完成，由我记录”等语义时进入高置信候选；Phase 1 不自动关闭跨 owner 任务，而是生成 `WAITING_CONFIRMATION` 或 Agent 追问。

### 7.4 FollowUpTaskQueryService

职责：

- 提供 Agent 查询任务的确定性接口。
- 支持 today / this_week / next_week / overdue / open / completed / customer_scope。
- 统一权限过滤。
- 返回结构化任务和可选证据摘要。

### 7.5 WorkSummaryService

职责：

- 汇总指定时间范围内用户完成的工作。
- 数据源包括跟进任务、客户活动、商机事件、合同、回款、发票、License 等。
- 输出结构化事实，交给 Agent 做自然语言总结。

## 8. LangGraph 编排

### 8.1 与现有客户活动 AI 整理 workflow 的关系

现有系统已经有 `customer_activity_ai_workflow`，页面创建活动和 Agent 创建活动都会触发客户活动 AI 整理。该 workflow 负责：

- 将原始 `source_content` 整理成 `content_json`、`summary`、`title`。
- 从原文抽取 `next_action`。
- 在用户未明确填写下次跟进时间时，从原文时间表达解析 `next_follow_time`。
- 更新客户活动向量证据和活动有效性评估。

销售承诺管理不应另起一套活动整理逻辑，而应接在客户活动整理 workflow 后面。

推荐触发顺序：

1. 页面或 Agent 创建/更新 `CustomerActivity`。
2. 如果活动已有显式 `next_action` 或 `next_follow_time`，触发一次确定性任务投影。
3. 触发现有 `customer_activity_ai_workflow` 做活动整理。
4. `persist_structured_content` 完成后，触发销售承诺/任务投影。
5. 投影服务根据最终活动字段和幂等 key 创建、更新或跳过任务。
6. 活动有效性评估可以继续独立执行，不阻塞任务投影。

这样页面录入和 Agent 录入共享同一条后处理链路：入口不同，落点都是客户活动；任务生成只认客户活动最终状态，不认入口来源。

### 8.2 跟进活动后处理 graph

建议新增 `customer_activity_commitment_graph`。

节点：

1. `load_activity`

   加载客户活动、客户、活动归属人、客户负责人、最近活动和业务上下文。活动归属人用于任务 owner，客户负责人用于客户上下文和权限判断。

2. `extract_commitments`

   使用 LLM structured output 抽取承诺和下一步动作。

3. `resolve_temporal`

   将“下周三”“月底”“节后”等时间表达解析为确定日期，并保留原文。

4. `retrieve_open_tasks`

   查同客户未完成任务。

5. `semantic_match`

   使用结构化候选、向量证据和 LLM 判断新活动与旧任务的关系。

6. `decide_transition`

   输出任务状态迁移计划。

7. `human_confirmation_policy`

   判断是否需要 Agent 追问用户。

8. `persist_projection`

   写入 commitments、follow_up_tasks、task_events 和向量证据元数据。

9. `emit_agent_followup`

   如果需要追问，将问题交给 Agent 会话或 IM 入口。

基于误关任务和过度追问的产品风险隔离，Phase 1 不启用完整 `semantic_match`、`decide_transition` 和 `emit_agent_followup`。Phase 1 graph 收敛为：

1. `load_activity`
2. `read_final_next_step_fields`
3. `project_commitment_and_task`
4. `persist_projection`

其中 `read_final_next_step_fields` 必须读取 AI 整理后已经持久化的活动字段。

### 8.3 Agent 查询 graph

用户自然语言查询任务时，Agent 应按以下流程：

1. 识别查询意图和时间范围。
2. 将自然语言时间转换为确定 range。
3. 调用任务查询 tool 或工作总结 tool。
4. 如用户问题带语义条件，例如“预算相关”“卡在试用反馈”，调用向量检索补充候选。
5. 合并结构化结果和语义证据。
6. 输出可读总结，必要时附客户和任务列表。

全局只读查询需要在主 Agent graph 中确定性路由，而不是完全交给 LLM 自由选择：

- “今天我的任务有哪些”“本周我的任务有哪些”“下周有什么工作安排”“还有哪些客户要跟进”“未完成/逾期任务”等问题，路由到 `list_follow_up_tasks`。
- “本周我完成了什么”“今天我做了什么”“帮我生成周报/月报”“本月工作总结”等问题，路由到 `summarize_completed_work`。
- 如果问题同时包含“完成了什么”和“任务/待办/安排/要跟进/未完成/逾期”等任务词，优先按任务查询处理，避免把“我的任务有哪些”误答成工作总结。
- 只读 tool 执行必须发生在持有 db、authorization、tool registry 和 user/team/session 上下文的主 Agent graph；后续 action planning graph 只负责把 tool result 格式化为最终回复。
- 只读查询路由只接受规范化后的 `CRM_READ_QUERY` 意图，并继续读取 `read_query.type` 区分任务查询、工作总结、客户档案、商机、合同、回款等二级查询类型，避免把“客户查询”这个历史词继续扩展成泛读意图。
- 明确客户范围的问题不要在客户解析前直接走全局查询。已采用二段只读路由：先 resolve customer，再把客户 public id 通过 `customer_id` 参数传入 `list_follow_up_tasks` 或 `summarize_completed_work`。
- 如果 customer parser 把“下周我还有哪些客户要跟进”这类通用查询片段误识别为客户名，应识别为非明确客户范围，继续允许走全局任务查询。

这个路由层的职责是“决定应该读哪个事实源”，不是生成事实。任务状态、完成状态、owner 权限、客户可见性和时间窗口仍由只读 tool 与底层 service 判断。

架构要求：

- Semantic parse 的一级意图只表达大类：写入型业务动作、只读 CRM 查询、未知/澄清等。泛读查询统一使用 `CRM_READ_QUERY`。
- `read_query.type` 是只读查询的二级语义，不应再新增 `CUSTOMER_QUERY`、`TASK_QUERY`、`WORK_SUMMARY_QUERY` 这类并列一级意图。
- 旧 `CUSTOMER_QUERY` 只允许在 schema 或子图输入适配边界归一化为 `CRM_READ_QUERY`，不得作为业务路由、trace 展示或前端文案继续传播。
- 主 Agent graph 负责 LangGraph 状态编排和 tool 执行；`AgentReadQueryPlanner` 负责把 `CRM_READ_QUERY + read_query.type` 转成一个确定性只读 tool plan；tool/service 负责事实读取；presenter 负责把 tool result 转成自然语言回复。
- Trace 对外展示业务标签，例如“任务查询”“工作总结”“客户查询”；内部事件保留 `technical_intent=CRM_READ_QUERY`，便于排查但不把技术枚举直接暴露给用户。

## 9. Agent Tools

建议新增工具：

工具接口约定：

- tool 入参和出参统一使用业务实体 `public_id`，例如 `customer_public_id`、`task_public_id`、`commitment_public_id`。
- tool 内部负责将 public_id 解析为数据库主键 id，并在解析后执行 team、客户访问、任务 owner 等权限校验。
- tool 输出可以包含 `id` 字段给 Agent 展示，但该 `id` 应是 public_id；不要把数据库主键暴露给 LLM 上下文。
- 向量检索 metadata 中保存 public_id，结构化数据库查询再通过 public_id 回表拿最新状态。

### 9.1 list_follow_up_tasks

只读工具。

典型触发问题：

- “今天我的任务有哪些”
- “本周我的任务有哪些”
- “下周有什么工作安排”
- “还有哪些客户要跟进”
- “我还有哪些任务没完成”
- “哪些跟进已经逾期”

输入：

- range_type: `today` / `this_week` / `next_week` / `custom`
- start_at
- end_at
- status_filter
- customer_public_id
- customer_query
- semantic_query
- limit

输出：

- tasks
- overdue_count
- due_today_count
- evidence_summary

### 9.2 get_follow_up_task_detail

只读工具。

输入：

- task_public_id

返回单个任务的来源活动、相关承诺、最近证据和状态历史。

### 9.3 resolve_follow_up_task

写入工具，必须有明确用户输入或确认。

输入：

- task_public_id

支持：

- complete
- snooze
- cancel
- keep_open
- create_follow_up_and_complete

### 9.4 list_completed_work

只读工具。

用于回答“本周我完成了什么”。

输入：

- window: `today | this_week | last_week | this_month | custom`
- start_at: `custom` 窗口开始时间，ISO 日期或日期时间
- end_at: `custom` 窗口结束时间；日期型按包含当天处理
- cursor: 上一页返回的 `next_cursor`
- include_tasks
- include_activities
- include_business_events
- limit

输出结构化工作事实，由 Agent 总结。

输出必须包含：

- items: 本页 structured facts
  - 每条 fact 包含 `fact_id`、`fact_type`、`source_group`、`occurred_at`、`customer`、`title`、`payload`
  - 每条 fact 包含 `attribution`，用于审计这条工作为什么归属于当前用户：
    - `user_id`
    - `field`
    - `source`
- source_counts: 本页按 fact_type 统计
- source_total_counts: 当前过滤条件下 MySQL 可用事实总数
- available_total
- truncated
- next_cursor
- pagination

当 `truncated=true` 时，Agent 必须继续用 `next_cursor` 拉取后续 facts，或明确告知用户当前总结只基于部分事实。

### 9.5 summarize_completed_work

只读工具。

用于回答“本周我完成了什么”“生成本月工作总结”“帮我整理周报”等需要自然语言总结的场景。

典型触发问题：

- “本周我完成了什么”
- “今天我做了什么”
- “帮我生成周报”
- “本月工作总结”
- “这个月客户推进情况总结”

输入与 `list_completed_work` 保持一致，额外支持：

- question: 用户原始问题

处理规则：

- 先调用 `WorkSummaryService.list_completed_work` 获取 MySQL structured facts。
- 再调用 `WorkSummaryNarrativeService` 生成自然语言总结。
- LLM 只能基于 `facts.items` 总结，不能使用向量证据、外部知识或临时猜测。
- 每个总结项必须包含 `fact_ids`，并且只能引用 `facts.items` 中真实存在的 `fact_id`。
- LLM 返回后，服务端必须二次 grounding：过滤无效 `fact_id`；如果没有任何有效引用，退回确定性 fallback。
- 当 `facts.truncated=true` 时，总结必须标记缺少后续分页事实，不能声明完整。

输出：

- facts
- narrative.answer
- narrative.highlights
- narrative.customer_summaries
- narrative.citations
- summary_source
- fallback_reason

### 9.6 work_summary_golden

本地质量门禁，不作为普通业务 API 暴露。

用于验证“本周我完成了什么”“生成周报/月报”等工作总结场景是否仍满足事实契约。

评测对象：

- `WorkSummaryService.list_completed_work` 产出的 structured facts。
- `WorkSummaryNarrativeService` 或确定性 fallback 产出的 narrative。
- 人工校正样本的结构化可回放性。

评测指标：

- `fact_recall`
- `citation_completeness`
- `hallucination_rate`
- `owner_attribution_errors`
- `time_window_errors`
- `classification_errors`
- `correction_actionability`

运行方式：

- `CRM-Server/scripts/run_work_summary_eval.py`
- 默认 fixture：`CRM-Server/tests/fixtures/work_summary_golden_cases.json`
- 可选 `--persist` 写入 evaluation run 表，使用 `suite_name=work_summary_golden` 区分。

人工校正规则：

- 纠错先记录为结构化反馈，不直接改历史事实，不直接改 prompt。
- 支持 `missing_fact`、`remove_fact`、`reclassify_item`、`rewrite_summary`、`time_window_fix`、`owner_scope_fix`、`citation_fix`。
- 除 `missing_fact` 外，纠错必须能指向真实 `fact_id`。
- 校正样本后续进入 golden suite，作为 prompt、事实源规则和读模型调整的回归样本。

## 10. LLM 使用要求

LLM 输出必须使用 Pydantic structured output。

关键 schema：

- CommitmentExtractionResult
- TaskMatchDecision
- TaskTransitionPlan
- UserResolutionIntent
- WorkSummaryNarrative

`TaskMatchDecision` 至少包含：

```json
{
  "relationship": "FULFILLED|PARTIALLY_FULFILLED|SNOOZED|CANCELLED|UNRELATED|UNCLEAR",
  "confidence": 0.0,
  "matched_task_ids": [],
  "evidence_activity_ids": [],
  "reason": "",
  "needs_user_confirmation": false
}
```

自动关闭任务建议阈值：

- confidence >= 0.85：可自动关闭，但必须记录证据。
- 0.60 <= confidence < 0.85：进入确认策略。
- confidence < 0.60：默认不关闭。

追问策略不应过度打扰用户。建议只在以下情况下触发：

- 旧任务已逾期。
- 旧任务今天到期。
- 旧任务 priority 为 HIGH。
- 新跟进与旧任务无关，但旧任务与当前客户核心推进相关。

## 11. 历史跟进数据处理

现有系统已经有客户活动和从线索迁移来的跟进数据，部分记录包含 `next_action` 和 `next_follow_time`。上线新方案时需要处理历史数据，否则 Agent 查询“我还有哪些客户要跟进”会漏掉已经存在的下一步安排。

### 11.1 历史数据分类

按客户活动历史记录分为：

1. 有 `next_follow_time` 且有 `next_action`

   优先生成 follow-up task。

2. 有 `next_follow_time` 但没有 `next_action`

   生成低置信任务，标题可从活动摘要和原文中抽取；如果无法抽取动作，默认标题为“跟进客户进展”。

3. 有 `next_action` 但没有 `next_follow_time`

   生成 commitment，但不生成开放任务；如产品决定需要展示，可单独在 Agent 查询“无下次安排但有下一步动作”时展示，不进入今天/本周强任务列表。

4. 没有 `next_action` 也没有 `next_follow_time`

   不生成任务。只作为语义证据和工作总结来源。

### 11.2 历史任务状态推断

对历史记录不能简单把所有 next_follow_time 都当成未完成任务。需要按同一客户时间线推断。

建议规则：

1. 按 team_id、customer_id、owner_id、occurred_at 升序处理历史客户活动，其中历史客户活动的 owner_id 第一版由 `creator_id` 派生。
2. 某条活动产生了任务 A。
3. 如果任务 A 的 due_at 之后存在同客户、同 owner 的后续活动，使用 reconciliation 逻辑判断后续活动是否完成 A。
4. 如果无法高置信判断完成，但存在明显后续跟进记录，可将任务标记为 `SUPERSEDED` 或 `HISTORICAL_CLOSED`，避免把大量旧任务堆到用户今日待办。
5. 对最近未被后续活动覆盖的任务生成 `OPEN`。
6. Phase 1 只把最近 90 天的历史任务作为开放候选；更早的数据进入向量证据和工作总结，不直接形成待办压力。
7. 每个客户、每个 owner 最多只维护最新 1 条历史开放安排。更早的同客户同 owner 历史任务默认标记为 `HISTORICAL_CLOSED` 或 `SUPERSEDED`，避免历史回填制造重复待办。

### 11.3 历史回填策略

建议分阶段回填：

第一阶段：结构化回填

- 只处理有 `next_follow_time` 的客户活动。
- 只对每个客户、每个活动归属人最近一条未被覆盖的下一步安排生成 OPEN 任务。
- 如果历史活动有 `owner_id`，任务 owner 使用该活动 `owner_id`；如果历史活动没有 `owner_id`，先用 `creator_id` 初始化活动 `owner_id`，再用于任务归属。
- 没有明确 `next_follow_time` 的历史活动先不生成开放任务；只有 `next_action` 但无时间的历史活动可沉淀为 commitment 或 evidence，不进入强待办。
- 线索 follow-up 不纳入 Phase 1 回填范围；后续扩展线索任务时再新增 source type 和回填策略。
- 老旧任务默认不打扰用户。

第二阶段：LLM 批量回填

- 对最近 90 天高价值客户活动运行 commitment extraction。
- 抽取承诺和任务。
- 对同客户后续活动运行 match。
- 低置信不生成 OPEN 任务，只入 evidence。

第三阶段：用户确认

- Agent 可以回答：“我从历史跟进中发现 12 个可能还没处理的安排，要不要帮你整理成待办？”
- 用户确认后再批量激活，避免突然出现大量历史任务。

### 11.4 回填幂等

历史回填必须可重复执行。

建议使用唯一键或幂等 key：

- commitment source key: `team_id + source_activity_id + commitment_hash`
- task source key: `team_id + source_activity_id + task_hash`

回填脚本应只通过正式 service 写入，不能绕过业务规则直接批量插表。

## 12. 权限和归属

### 12.1 归属原则

任务归属应以跟进记录的归属人为主，而不是客户负责人。

原因：

1. 当前客户支持团队成员协作，同一个客户可能同时有销售、售前、交付、支持等角色参与。
2. 下一步动作本质上是某次跟进中产生的工作承诺，应该归属于做出或记录这个承诺的人。
3. 如果售前跟进销售负责的客户，售前记录中产生的“下周演示”“补充方案”应属于售前；销售自己记录的“确认预算”“推进采购流程”应属于销售。
4. 使用客户 owner 作为默认任务 owner，会把多人协作场景压扁成单负责人模型，导致任务误分配、工作总结失真，也会让 Agent 的“我的任务”回答不可信。

Phase 1 归属决策：

1. 引入业务概念 `follow_up_owner_id`，表示跟进记录对应的工作归属人。
2. Phase 1 给 `CustomerActivity` 补充独立 `owner_id`，该字段就是活动层的 `follow_up_owner_id`。
3. `crm_sales_commitments.owner_id` 和 `crm_follow_up_tasks.owner_id` 均由 `follow_up_owner_id` 派生。
4. 客户 `owner_id` 不作为任务默认归属，只作为客户访问控制、客户上下文、负责人展示和管理查询维度。
5. 当前页面和 Agent 默认 `owner_id = creator_id = current_user.id`；未来支持“代记录”或“指派给某人跟进”时，只需要显式传入活动 `owner_id`，任务投影规则不变。
6. 历史客户活动迁移时，用活动 `creator_id` 初始化活动 `owner_id`。
7. 任务和承诺实体自身也保留 `creator_id`，用于审计“谁创建了这条任务/承诺”；查询“我的任务”仍以 `owner_id` 为准，不以 `creator_id` 为准。

### 12.2 跨成员协作规则

同一客户下允许存在多个成员各自的开放任务。

自动生成任务：

- 售前创建跟进记录，生成售前自己的任务。
- 销售创建跟进记录，生成销售自己的任务。
- 客户负责人不是任务归属判断的默认来源。

自动关闭或延期任务：

- 默认只匹配同 team、同 customer、同 owner 的开放任务。
- 如果新跟进与当前用户自己的旧任务相关，Agent 可以自动关闭旧任务并生成新的下一步任务。
- 如果新跟进明显提到另一个成员的任务已经完成，不建议直接关闭对方任务；应进入 `WAITING_CONFIRMATION`，或由 Agent 询问任务 owner / 当前用户确认。
- 如果用户明确表达“这个任务转给我”“后续我来跟”，可以创建任务转移事件，保留原 owner、原任务来源和转移原因。

### 12.3 查询权限

查询需要同时区分“可见范围”和“任务归属”：

- “我的任务”“我还有哪些客户要跟进”：只返回 `task.owner_id == current_user.id` 的任务，并且客户仍需在当前用户可访问范围内。
- “这个客户还有哪些任务”：在用户有权访问该客户的前提下，返回该客户可见任务，并按 owner 分组展示，避免误以为都是自己的任务。
- “本周我完成了什么”：以当前用户创建/归属的跟进记录、完成的任务和相关业务事件为主。
- “我创建了哪些任务”：未来如开放指派能力，应按 `creator_id == current_user.id` 查询，这是审计和管理视角，不等同于待办归属。
- 管理者查询团队任务时，可按成员聚合，但 Agent 回答必须说明查询范围和成员维度。
- 普通销售不能仅因为能访问客户，就操作或关闭别人的任务；跨 owner 操作需要显式权限或确认流程。
- 任务 tool 必须复用现有团队和客户权限边界。

## 13. 前端范围

Phase 1 不新增完整任务管理页面。

可选前端增强：

- Agent 回复中展示任务列表卡片。
- 客户详情中展示“当前下一步安排”小块。
- 客户列表增加可选筛选项：需跟进、已逾期、无下次安排。

不建议第一版做：

- 独立任务看板。
- 复杂任务表格。
- 手动任务 CRUD。
- 重型提醒中心。

## 14. 分阶段实施

### Phase 1：结构化任务投影

- 新增 `crm_sales_commitments`、`crm_follow_up_tasks`、`crm_follow_up_task_events`、`crm_follow_up_task_projection_runs`。
- 给 `crm_customer_activities` 补充 `owner_id`，历史活动用 `creator_id` 初始化 owner。
- 客户活动创建/更新后进入统一投影流程，第一版优先使用已有或 AI 整理后的 `next_action` 和 `next_follow_time`，LLM commitment extraction 可作为增强但不阻塞最小闭环。
- 客户活动删除或清空下一步字段后，同源开放任务进入取消或替代状态，不保留失去来源依据的开放任务。
- 页面录入、Agent 录入、AI 创建客户附带跟进、历史回填都复用同一个 FollowUpTaskProjectionService。
- Agent 支持查询今天、本周、下周、逾期和未完成任务。
- 历史数据做结构化回填：最近 90 天、每客户每 owner 最多 1 条最新开放安排，线索 follow-up 暂不纳入。
- 不在 Phase 1 自动关闭旧任务；旧任务状态以生成、查询、历史回填和审计为主，避免第一版就引入误关风险。

### Phase 2：自动关闭和低置信追问

- 新增 reconciliation graph。
- 新跟进自动关闭相关旧任务。
- 无关旧任务在到期/高优先级时触发低打扰追问。
- 支持用户自然语言延期、取消、保留、补充进展。
- 追问业务逻辑只实现一套，Agent 会话、IM Bot、后续其他入口只是触达渠道；不同渠道不能产生不同状态迁移规则。

### Phase 3：向量证据和语义查询

- 将 commitment 和 follow_up_task 写入向量证据。
- 支持“预算相关”“试用反馈”“采购卡住”等语义任务查询。
- 任务回答中补充上下文证据。

### Phase 4：工作总结

- 支持本周完成内容总结。
- 合并任务完成、跟进记录、商机推进和后续业务事件。
- 输出适合销售复盘和管理者查看的摘要。

### Phase 5：主动摘要和偏好记忆

- 每日摘要、周报和低打扰提醒策略。
- 用户偏好记忆，例如默认跟进间隔、提醒敏感度、常用时间表达偏好。
- 该阶段处理主动摘要、周期提醒和偏好记忆；与 Phase 2 的任务确认追问共用触达治理，但不复写任务业务逻辑。

## 15. 验收标准

第一版验收：

1. 用户通过 Agent 问“今天我的任务有哪些”，能得到基于结构化任务表的准确结果。
2. 用户通过 Agent 问“本周我的任务有哪些”“下周有什么工作安排”“还有哪些客户要跟进”，能得到正确时间范围和权限范围内的结果。
3. 创建带 next_action 和 next_follow_time 的客户活动后，系统自动生成跟进任务。
4. 历史客户活动中最近未覆盖的下一步安排被回填为任务。
5. Agent 查询结果不会依赖实时扫描全量跟进记录。
6. 任务状态变更有事件审计。
7. 低置信 LLM 判断不会自动关闭任务。
8. 同一客户由不同成员分别负责跟进记录时，生成的任务分别归属对应活动 owner，不会默认归属客户负责人。
9. 用户从页面手工创建活动并填写下次跟进时间/动作时，也能生成任务。
10. 用户从页面手工创建活动但只在原文中写了下一步动作和时间时，AI 整理完成后能回写字段并触发任务投影。
11. 用户创建活动且最终没有下一步动作和下次跟进时间时，不生成任务，并记录跳过原因。
12. 同一客户活动的保存后确定性投影、AI 整理后投影和历史回填投影都能在投影运行表中查到状态、输入 hash、跳过原因或失败原因。
13. 用户更新或删除客户活动后，同源开放任务能被更新、取消或替代，不产生重复开放任务。
14. Agent 查询“今天”“本周”“下周”“逾期”时，时间范围按用户或团队时区一致计算。
15. Phase 1 历史回填只处理最近 90 天客户活动，并且每客户、每 owner 最多生成 1 条最新开放安排。
16. 客户活动有独立 `owner_id`，任务和承诺 owner 从活动 `owner_id` 派生；历史活动用 `creator_id` 初始化 owner。

第二版验收：

1. 新跟进能自动关闭语义相关旧任务。
2. 新跟进与旧任务无关且旧任务到期时，Agent 能追问用户。
3. 用户自然语言回复“下周五再说”“不用管了”“已经确认了”等，系统能正确延期、取消或完成任务。
4. Agent 能回答“本周我完成了什么”，且结果综合任务、跟进记录和业务事件。

## 16. 实施准备评审

当前方案已经可以进入第一版实施准备，但建议按“结构化任务投影先行，语义自动流转后置”的方式落地。

### 16.1 已经明确的设计决策

1. 用户主工作流仍是跟进记录，不新增强制任务维护动作。
2. 任务查询事实源是 MySQL 任务表，不实时扫描全量跟进记录。
3. 承诺和跟进任务分表，承诺保存语义事实，任务保存可执行安排。
4. 任务 owner 来自跟进记录归属人；Phase 1 给客户活动补充 `owner_id`，历史活动用 `creator_id` 初始化。
5. 任务和承诺实体第一版即提供 `public_id`，Agent/tool/API 不暴露数据库主键。
6. 任务和承诺实体保留 `creator_id`，为未来指派、Agent 代创建和审计预留。
7. 自动关闭旧任务放到 Phase 2，第一版先避免误关任务。
8. 投影运行使用独立 `crm_follow_up_task_projection_runs`，不把 pipeline 状态塞进客户活动表。

### 16.2 第一版最小可交付范围

Phase 1 只做以下闭环：

1. 新增四张表和迁移：commitments、follow_up_tasks、follow_up_task_events、follow_up_task_projection_runs。
2. 给客户活动补充 `owner_id`，历史活动使用 `creator_id` 初始化 owner。
3. 客户活动创建或更新后，基于 `next_action` / `next_follow_time` 生成或更新开放任务。
4. 客户活动 AI 整理完成后，再基于最终字段执行一次幂等投影。
5. 如果活动最终没有 `next_action` 和 `next_follow_time`，不生成任务，并记录跳过原因。
6. 如果活动更新后清空下一步字段，或活动被删除/作废，更新或取消同源开放任务。
7. Agent tool 支持查询我的今天、本周、下周、逾期、未完成任务，时间范围按用户或团队时区计算。
8. 历史客户活动按 owner 回填最近 90 天每客户每 owner 最新 1 条开放安排。
9. 任务生成、跳过、回填、状态变更写入任务事件表和投影运行表。
10. API 和 Agent tool 只使用 public_id。

第一版暂不做：

- 独立任务管理页面。
- 手动任务 CRUD。
- 低置信追问。
- 自动关闭旧任务。
- 跨 owner 任务关闭。
- 主动每日提醒。
- 复杂语义任务搜索。
- 线索 follow-up 投影。
- 非客户跟进来源的通用任务。
- 管理者团队任务查询权限码。

### 16.3 开发拆分建议

详细 ticket 拆分见：`CRM-Docs/requirements/2026-08-06-sales-commitment-management-task-breakdown.md`。

建议按以下顺序实施：

1. 数据库迁移和 ORM model。
2. 客户活动 `owner_id` 迁移和历史数据初始化。
3. public_id 生成、schema 和 CRUD。
4. 投影运行表和投影作业模型。
5. FollowUpTaskProjectionService，先实现确定性投影。
6. 接入客户活动创建/更新后的保存后确定性投影入口。
7. 接入 `customer_activity_ai_workflow.persist_structured_content` 后的最终投影入口。
8. FollowUpTaskQueryService 和 Agent tools。
9. 历史回填脚本，复用正式 service。
10. 最小验收测试和权限测试。
11. 再进入 Phase 2 的 reconciliation graph 和 LLM match。

### 16.4 失败处理和观测

客户活动保存不能被任务抽取失败阻塞。

建议：

- 活动保存成功后，如果已有显式下一步字段，异步触发保存后确定性任务投影。
- 客户活动 AI 整理完成并持久化结构化字段后，异步触发最终任务投影。
- 任务投影失败时在投影运行表记录状态、错误原因、输入快照 hash 和重试次数。
- 同一活动重复触发时依赖唯一键和 hash 幂等。
- Agent 查询任务时只读任务表，不临时触发大范围重算。
- 需要有管理侧或日志查询能力，能排查某条活动为什么没有生成任务。

Phase 2 自动/确认状态迁移需要独立于投影运行的安全观测。

已补充第一层实现：

- `FollowUpTaskTransitionObservabilityService` 从任务事件、确认 Case 和确认提示投递日志汇总自动迁移、人工确认迁移、回滚、确认处理和提示触达比例。
- 新增 `crm_follow_up_task_transition_policy_decision_logs` 作为自动迁移策略决策事实源，记录每次策略判断的开关状态、allowlist 命中、action、允许/阻断结果、reason、配置错误和完整决策快照；策略服务仍只负责读配置和判断，自动化编排在拿到策略结果后显式写入该日志。
- 观测汇总已纳入策略决策日志，输出策略决策总量、允许/阻断数量、允许率、按 reason/action/enabled/owner allowlist 分组和配置错误总量。
- 新增 `crm_follow_up_task_reconciliation_runs` 作为候选检索和 deterministic reconciliation 输入的运行事实源，使用 `trr_` public_id，记录 owner、actor、source activity、窗口、跨 owner 配置、候选 public_id 快照、过滤条件、使用策略、状态、skip reason 和耗时。
- 新增 `crm_follow_up_task_llm_matcher_runs` 作为 LLM semantic matcher 运行事实源，使用 `tlm_` public_id，记录 source、decision、候选 public_id、置信度、是否需确认、禁止自动迁移原因、证据词、评测失败项、模型名、结构化输出策略、schema error 类型/摘要和耗时。
- 观测汇总已纳入 reconciliation run trace 和 LLM matcher/schema error 日志，输出 run 数、状态分布、skip reason、跨 owner 候选、候选总量、LLM source/decision/model/schema error 分布、确认比例、评测失败总量、置信度和耗时。
- `GET /v1/follow-up-task-transition-observability/summary` 作为只读运维接口，支持按 team、时间窗口和 `owner_scope=team|mine` 查询，复用任务排查权限。
- 汇总结果只返回聚合数、业务 owner 和必要的事件 public_id，不暴露任务、Case、来源活动等内部数据库主键。
- `metric_gaps` 当前为空；feature flag / policy decision、reconciliation run trace、LLM schema error 均已有独立事实源，不能再用任务事件反推伪造这些指标。

### 16.5 主要剩余风险

1. 当前客户活动没有 public_id，短期不阻塞任务表设计，但会限制 Agent 精确引用来源跟进记录。
2. 客户活动新增 `owner_id` 后，需要确保现有页面、Agent tool、历史迁移和权限校验都按 owner/creator 分离后的语义处理。
3. 历史回填即使限制为 90 天，也需要坚持每客户每 owner 最新 1 条开放安排，避免制造大量过期待办。
4. 自动关闭旧任务依赖 LLM 判断，必须放在 Phase 2 并保留确认策略。
5. 如果 Agent tool 权限只校验客户可见性，不校验任务 owner，会出现能看客户就能操作别人任务的问题。

### 16.6 非成本驱动的取舍复核

以下决策不是为了降低实现工作量，而是为了保证体验、正确性和后续演进空间：

1. 统一由 `FollowUpTaskProjectionService` 负责幂等写入。

   这个设计应保留。页面录入、Agent 录入、客户活动 AI 整理完成、用户更新活动、历史回填都会触发任务投影。如果每个入口各自处理幂等和写表，后续会出现重复任务、权限归属不一致和回填逻辑漂移。统一 service 是长期正确边界。

2. 投影状态不写入客户活动表。

   这个设计应调整为独立投影运行表。客户活动表只表达跟进记录事实；投影运行表表达 pipeline 事实。这样后续增加 LangGraph 节点、LLM 提取版本、重试、回填批次、向量写入状态时，不会污染活动表，也不会丢失多次运行的排查上下文。

3. Phase 1 不自动关闭旧任务。

   这个不是能力不足，而是为了保护用户体验。误关闭任务比暂时不自动关闭更严重，会直接破坏用户对“我的任务”的信任。自动关闭、延期和跨 owner 流转应进入 Phase 2，并带置信度、证据、事件审计和确认策略。

4. 没有明确时间的 `next_action` 不进入强待办。

   这是语义正确性问题。没有 due_at 的事项可以沉淀为 commitment，并在 Agent 查询“无下次安排但有下一步动作”时展示；不应混入今天、本周、逾期这类强时间任务，避免制造噪音。

5. LLM 能力从一开始按可替换节点设计。

   Phase 1 可以优先使用现有客户活动 AI 整理后的 `next_action` 和 `next_follow_time`，但数据模型、投影运行表和 graph 节点必须预留 `CommitmentExtractionService`、模型版本、输入快照和证据字段，避免后续接入更强抽取能力时重做表结构。

### 16.7 Phase 1 工程验收门槛

Phase 1 开发完成后，除产品验收外，还需要通过以下工程验收。未满足这些条件时，不应进入自动关闭旧任务、低置信追问或主动提醒等后续阶段。

1. 幂等验收

   同一客户活动在以下场景重复触发投影时，不得重复生成 commitment 或 follow-up task：

   - 活动创建后立即触发保存后确定性投影。
   - 客户活动 AI 整理完成后再次触发最终投影。
   - 用户更新活动后重新投影。
   - 用户清空活动下一步字段或删除活动后重新投影。
   - 历史回填脚本重复执行。
   - 异步任务失败后重试。

   验收标准：同一 `team_id + source_type + source_activity_id + task_hash` 只生成一条业务任务；重复触发只更新已有任务或记录 `SKIPPED / DUPLICATE / SUPERSEDED_INPUT` 投影运行结果。

2. 权限和归属验收

   “我的任务”必须按任务 `owner_id` 查询，不按客户 `owner_id` 或任务 `creator_id` 查询。用户能访问客户，不代表可以关闭、延期或取消别人的任务。

   验收标准：

   - 售前在销售负责的客户下创建活动，生成售前自己的任务。
   - 销售在同一客户下创建活动，生成销售自己的任务。
   - 销售查询“我的任务”不出现售前任务。
   - 用户查询客户任务时可以按权限看到客户范围内的任务，但跨 owner 操作必须被拒绝或进入确认流程。

3. 页面录入和 Agent 录入一致性验收

   页面手工添加活动和 Agent 创建活动必须进入同一套后处理链路，不能各自维护任务生成逻辑。

   验收标准：

   - 页面显式填写 `next_action` / `next_follow_time`，活动保存后可生成任务。
   - 页面只在原文中写下一步动作和时间，AI 整理回写字段后可生成任务。
   - Agent 创建活动并传入下一步字段后，也通过同一个 `FollowUpTaskProjectionService` 生成任务。
   - 页面和 Agent 两种入口生成的任务字段、owner、creator、事件和投影运行记录规则一致。

4. AI 整理后补投影验收

   任务投影必须以客户活动最终结构化字段为准。活动保存时没有显式下一步字段，但 AI 整理从原文抽取出 `next_action` 或 `next_follow_time` 后，应触发最终投影。

   验收标准：

   - 保存时无下一步字段、AI 整理后有下一步字段：生成任务或 commitment。
   - 保存时已有下一步字段、AI 整理后字段被修正：更新已有任务，不重复创建。
   - AI 整理失败：如果保存时已有显式下一步字段，保存后确定性投影的任务仍然存在。
   - AI 整理后仍无下一步字段：不生成任务，并在投影运行表记录跳过原因。

5. 活动更新和删除验收

   客户活动更新、清空下一步字段或删除后，任务列表不能残留失去来源依据的开放任务。

   验收标准：

   - 修改活动下一步动作或下次跟进时间：更新同源开放任务，并写入 `UPDATED` 事件。
   - 清空活动下一步动作和下次跟进时间：取消或替代同源开放任务，并记录 `SOURCE_NEXT_STEP_REMOVED`。
   - 删除或作废活动：取消同源开放任务，并记录 `SOURCE_ACTIVITY_DELETED`。
   - 已完成任务不因来源活动删除而物理删除，只补充审计信息。

6. 投影运行观测验收

   每次投影触发都必须有 `crm_follow_up_task_projection_runs` 记录，用于排查任务生成、跳过、失败和重试。

   验收标准：

   - 可按客户活动查到所有投影运行记录。
   - 可按 `FAILED` 状态查询失败运行并重试。
   - 运行记录包含 `trigger_type`、`input_snapshot_hash`、`projection_hash`、`status`、`skip_reason`、`error_message`、`attempt_count`、`started_at`、`finished_at`。
   - 不把投影 pipeline 状态写入 `crm_customer_activities` 作为唯一排查依据。

7. 历史回填低打扰验收

   历史回填不能突然制造大量过期待办，破坏用户对任务列表的信任。

   验收标准：

   - 回填脚本只通过正式 service 写入，不直接批量插任务表。
   - 回填可重复执行且幂等。
   - 回填窗口、开放任务候选规则和历史关闭规则可配置。
   - 老旧且低置信任务不进入 OPEN 强待办。
   - 每个客户、每个 owner 不应因为历史多条活动生成大量重复开放任务。

8. Agent 查询事实源验收

   Agent 回答任务问题必须先查结构化任务表，再用向量证据补充上下文，不能实时扫描全量跟进记录临时生成任务列表。

   验收标准：

   - “今天我的任务有哪些”“本周我的任务有哪些”“我还有哪些任务没完成”来自 `crm_follow_up_tasks`。
   - 逾期、今日、本周、下周按 `due_at` 和确定时间范围计算。
   - 语义条件如“预算相关”“试用反馈相关”可以使用 Qdrant 补充候选和解释，但最终任务状态仍以 MySQL 为准。

9. 时间口径验收

   Agent 和 API 对日期范围的理解必须一致，不能出现页面看是今天、Agent 回答成明天或逾期计算错位。

   验收标准：

   - “今天”“本周”“下周”按当前用户或团队时区转换为确定查询范围。
   - 只有日期粒度的任务按日期展示，不显示误导性的 00:00。
   - 逾期计算使用同一时区和 `due_at_granularity`。
   - 历史回填解析相对时间时使用活动发生时间和活动归属人的时区，不使用回填执行当天作为相对时间基准。

10. 回归测试门槛

   需要覆盖以下最小测试集：

   - 投影 service 幂等测试。
   - 页面活动创建触发投影测试。
   - AI 整理完成后触发最终投影测试。
   - 无下一步字段时跳过并记录原因测试。
   - 活动更新、清空下一步字段和删除后的同源任务处理测试。
   - 不同 owner 同客户任务隔离测试。
   - Agent task query tool 权限过滤测试。
   - 今天、本周、下周和逾期的时区边界测试。
   - 历史回填重复执行测试。

### 16.8 后续阶段工程验收框架

Phase 1 的工程验收门槛写得更细，是因为当前方案已经准备进入 Phase 1 开发。Phase 2 之后仍然需要独立验收门槛，只是应在进入对应阶段前，结合 Phase 1 的真实数据、误判样本和用户反馈进一步细化。

后续阶段不能直接在 Phase 1 基础上打开能力开关。每个阶段都需要先补充该阶段的详细设计、测试样本、回滚策略和验收标准。

#### Phase 2：自动关闭和低置信追问验收门槛

Phase 2 的核心风险是误关闭任务、误延期任务和过度追问用户。

进入 Phase 2 前必须补齐：

- reconciliation 评估契约和 golden case 基线。评估必须是纯确定性逻辑，不调用 LLM，不访问外部服务，不修改任务状态。
- `TaskReconciliationService` 的结构化候选规则、向量召回规则和 LLM rerank schema。
- 自动关闭、延期、取消、保留、等待确认的状态迁移表。
- 高置信自动变更阈值、低置信确认阈值和禁止自动变更场景。
- 跨 owner 任务处理策略和权限校验。
- 统一追问决策和触达渠道适配。Agent 会话、IM Bot 或未来其他入口只负责触达，不复制业务判断逻辑。
- 追问频率控制，避免同一客户、同一任务在不同渠道反复打扰。
- 回滚策略：被误关闭的任务必须可追溯、可恢复。

验收标准：

- 新跟进高置信完成旧任务时，旧任务可自动关闭，并写入 `closed_by_activity_id`、match confidence、证据和事件。
- 新跟进与旧任务无关但旧任务到期时，系统能通过 Agent 会话或 IM Bot 提出低打扰追问，且两种渠道使用同一套状态迁移逻辑。
- 用户自然语言回复“下周五再说”“先放着”“不用管了”“已经确认了”时，能正确延期、保留、取消或完成任务。
- 低置信、跨 owner、高价值客户和语义不完整场景不能自动改状态。
- 所有状态变更都有事件审计和投影/匹配证据。
- Phase 2 golden set 至少覆盖同 owner 完成、同 owner 延期、同客户无关新动作、跨 owner 需确认、低置信需确认；后续真实样本进入同一评测脚本。

#### Phase 3：向量证据和语义查询验收门槛

Phase 3 的核心风险是语义查询结果看起来智能，但事实状态不可靠。

进入 Phase 3 前必须补齐：

- commitment 和 follow-up task 写入 Qdrant 的 source type、metadata 和更新策略。
- 向量证据与 MySQL 任务状态的同步策略，避免展示已关闭或无权限任务。
- 语义查询 tool 的召回、回表、权限过滤和排序规则。
- 向量索引失败时的降级策略。

验收标准：

- “预算相关任务”“试用反馈相关客户”“采购卡住的客户”等查询能召回相关任务和证据。
- Agent 最终展示的任务状态以 MySQL 为准，不能只凭向量文档判断 OPEN / COMPLETED。
- 用户无权访问的客户、任务和证据不会通过语义检索泄露。
- 任务更新或关闭后，向量证据能更新或在回答时被结构化状态纠正。

#### Phase 4：工作总结验收门槛

Phase 4 的核心风险是把“任务完成清单”误当成真实工作结果，导致总结失真。

进入 Phase 4 前必须补齐：

- `WorkSummaryService` 的事实源范围：任务、客户活动、商机阶段、合同、回款、发票、License 等。
- 不同事实源的去重规则和优先级。
- “我完成了什么”和“团队完成了什么”的权限边界。
- LLM 总结 schema，要求先列事实再生成叙述。

验收标准：

- “本周我完成了什么”能同时覆盖已关闭任务、客户跟进记录和关键业务推进。
- 总结中的每个重点事项都能追溯到结构化事实或向量证据。
- Agent 不把未完成任务包装成已完成成果。
- 管理者视角和个人视角的统计口径清晰区分。

#### Phase 5：主动摘要和偏好记忆验收门槛

Phase 5 的核心风险是主动打扰、提醒疲劳和用户偏好误记。

进入 Phase 5 前必须补齐：

- 用户级提醒偏好、默认关闭策略和退订机制。
- 主动摘要触发条件、频率限制和安静时间。
- 偏好记忆的写入、更新、撤销和解释机制。
- 主动提醒失败、误提醒和重复提醒的审计。

验收标准：

- 默认不主动打扰用户，除非用户明确开启或产品确认默认策略。
- 用户可以自然语言调整提醒偏好，例如“以后每天早上提醒我今天要跟进的客户”。
- 同一任务不会被多个入口重复提醒。
- 用户可以查询和撤销 Agent 记住的跟进偏好。

结论：方案已经具备进入 Phase 1 开发的完整度。下一步不建议继续扩大 Phase 1 需求范围，应拆成实施 ticket。Phase 1 完成后必须先通过上述工程验收门槛；进入 Phase 2、Phase 3、Phase 4、Phase 5 前，也必须分别补充并通过对应阶段的详细工程验收。

## 17. 已确认决策和后续扩展边界

当前没有阻塞 Phase 1 实施的开放问题。以下为已确认决策：

1. Phase 1 给客户活动表增加独立 `owner_id`。

   活动 `owner_id` 表示跟进归属人，任务和承诺 owner 从活动 `owner_id` 派生；历史活动使用 `creator_id` 初始化 owner。

2. 历史回填窗口采用最近 90 天。

   Phase 1 只维护每个客户、每个 owner 最新 1 条开放安排。没有明确下一步时间的历史记录先不生成开放任务。

3. Phase 1 先围绕客户活动，不纳入线索 follow-up。

   线索 follow-up 后续作为新的 source type 扩展，不混入第一阶段客户跟进任务闭环。

4. 只有 `next_follow_time` 但没有明确 `next_action` 时，可以生成低置信任务。

   默认标题为“跟进客户进展”，并写入低置信度和 evidence；如果 AI 后续抽取出更明确动作，则更新任务标题和 action_text。

5. 低置信追问支持 Agent 会话和 IM Bot，但业务逻辑必须统一。

   Agent 和 IM 只是触达渠道，不应有不同的状态迁移、权限或确认规则。追问决策、频率控制、状态流转和事件审计应由同一套服务处理。

6. 管理者团队任务查询权限码后续扩展。

   Phase 1 优先保证个人任务查询和客户可见范围内的任务展示。管理者聚合查询需要单独权限设计后再开放。

7. 非客户跟进来源的通用任务后续扩展。

   Phase 1 不做手动创建通用任务，也不做非客户来源任务；后续如支持领导指派、内部事项或商机任务，通过扩展 `source_type` 和任务创建策略处理。
