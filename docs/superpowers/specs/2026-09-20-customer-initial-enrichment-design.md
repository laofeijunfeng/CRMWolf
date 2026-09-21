# 客户初始智能补全与行业历史回填

- 日期：2026-09-20
- 状态：已实施
- 范围：客户首次成为正式客户后的异步主数据补全；第一期只补 `Customer.industry`；完成后驱动客户档案投影。覆盖页面创建、Agent 创建、线索转客户、旧 AI 创建兼容入口和历史空行业客户。
- 上游决定：客户保存接口不等待 LLM；无人工确认、无置信度门槛；模型只能从启用行业目录选一个 code，业务上无法判断时选 `other`；技术失败不得伪装成 `other`；只补空值，人工值永不覆盖；首次补全优先，第一次技术失败后允许先生成无行业档案，后续补全成功再刷新档案。
- 相关规范：`CONTEXT.md`、`CRM-Docs/design-agent/foundations/architecture-boundary.md`、`CRM-Docs/design-agent/runtime/customer-intelligence-profile.md`
- 相关实现：`CRM-Server/app/api/customers.py`、`CRM-Server/app/services/customer_business_object_intelligence_service.py`、`CRM-Server/app/services/customer_intelligence_event_publication_service.py`、`CRM-Server/app/services/customer_intelligence_refresh_service.py`、`CRM-Server/app/services/agent/customer_profile_projection_graph.py`、`CRM-Server/app/models/customer_intelligence_run.py`、`CRM-Server/app/crud/industry.py`

## 1. 背景与目标

旧 `CustomerAIParser` 曾在创建客户时把 `industry_hint` 通过 `_match_industry()` 同步写入 `Customer.industry`，形成绕过 durable job、重试和审计的第二条行业补全路径。兼容入口继续解析和传递 `industry_hint`，但该字段不具备事实权威性，创建时必须保持 `CustomerCreate.industry=None`，统一由初始补全生命周期处理。

Agent 创建入口只迁入了普通客户创建 API；当原文没有明确行业时输出 `null`，即使输出行业也只能依赖普通 Customer CRUD 对 code 或精确名称的校验。统一异步补全因此承担目录闭世界和 durable lifecycle。

客户档案生成不会补写行业。档案把 `Customer.industry` 当作强事实输入，并且其架构契约明确：档案是只读投影，不是客户主数据真相。

目标：

1. 客户事务先完成并立即响应，LLM 补全不阻塞、不回滚客户。
2. 客户第一次成为正式客户时，异步补充缺失的主数据；第一期仅行业。
3. 行业直接写入，无人工确认、无置信度门槛；用户可在客户编辑页修改。
4. 补全逻辑可复用：未来增加公司规模、别名、组织简介等字段，不重建队列、租约、重试和审计。
5. 历史行业缺失（`NULL` 或仅空白字符）客户走同一 Workflow 批量补齐，而不是一次性 SQL。
6. 客户档案优先消费补全后的行业；补全技术失败时档案降级生成，后续成功再刷新。

## 2. 非目标

- 不让 `CustomerProfileProjectionGraph` 直接修改客户主表。
- 不让客户保存接口等待模型、重试或档案生成。
- 不新增人工审核页、确认卡或候选行业 UI。
- 不保存置信度，不以置信度决定是否写入。
- 不新增 `primary_industry` / `secondary_industry` 两个客户字段。客户只保存一个行业 code；二级行业的一级父行业由 `Industry.parent` 得出。
- 不覆盖任何已有有效行业，包括用户录入、线索转化继承和导入值；旧 AI 兼容入口的 `industry_hint` 不再同步写入。
- 不因普通编辑、跟进、商机、合同、回款或手动刷新档案而再次运行“初始补全”。
- 不为此引入 Celery、Redis 或新的消息中间件。
- 不把任意模型输出通过通用 `setattr()` 写入客户。

## 3. 方案选择

采用：**独立 durable `CustomerEnrichmentJob` + 可版本化 `CustomerInitialEnrichmentWorkflow`，复用现有数据库队列模式和客户智能事件边界。**

放弃：

1. **在创建 API 内同步调用 LLM**：增加延迟；模型故障会与客户保存纠缠。
2. **在档案 Projection Graph 内直接写 Customer**：违反“档案只读投影”，形成客户更新与档案刷新的循环。
3. **把行业补全直接塞进现有 `CustomerIntelligenceRun`**：当前 run 的 `UPDATING/FAILED/STALE` 语义都指向档案发布；补全应独立重试，同时允许档案先成功，两者生命周期不同。
4. **每个补全字段一个任务 / 一次模型调用**：未来扩字段会放大模型成本和调度复杂度。
5. **Alembic 或离线 SQL 直接写历史行业**：没有 LLM 语义、重试、审计和幂等，不可恢复。

## 4. 不变量

1. **客户事实优先。** 客户创建成功不因补全或档案失败而回滚。
2. **只填缺失值。** 字段 handler 统一定义 missing；v1 行业缺失是 `NULL` 或仅空白字符，自动补全只允许 missing → value，已有值永不覆盖。
3. **目录闭世界。** 行业输出必须是执行时启用的 `crm_industries.code`；业务无法判断时使用启用的一级行业 `other`。
4. **技术失败不是“其他”。** 模型不可用、超时、结构化输出错误、非法 code、目录缺失都进入重试；不得写 `other`。
5. **只在首次阶段运行。** 同一客户、同一 `plan_version` 最多一个 durable job；普通业务事件不创建新 job。
6. **人工修改优先。** 模型计算期间目标字段被填写时永久跳过；客户其它字段或版本变化时，本次旧判断不得写入，任务基于最新上下文重算。
7. **档案只读。** 补全 Workflow 负责主数据写入；Profile Workflow 只读取并投影。
8. **一套业务逻辑。** 新客户和历史回填使用同一 plan、同一模型合同、同一校验和写入服务。
9. **一次模型调用补多个字段。** 未来 plan 增加字段时，先收集全部缺失字段，再用一个 structured-output 调用返回结果。
10. **失败可恢复。** 任务有稳定幂等键、租约、重试、耗尽证据和服务重启恢复。

## 5. 总体流程

### 5.1 新客户

```text
客户创建事务
  → flush 得到 customer_id
  → savepoint 内 ensure CustomerEnrichmentJob
  → commit 客户事务
  → API 立即返回
  → post-commit kick enrichment worker
  → 登记/唤醒客户档案刷新
```

后台：

```text
CustomerEnrichmentJob (available_at = created_at + settle_seconds)
  → claim + lease
  → 重新读取客户最新上下文
  → 计算本 plan 当前缺失字段
  → 无缺失字段：SKIPPED
  → 一次 LLM structured output
  → 字段处理器校验
  → 条件写入仍为空的字段
  → COMPLETED / SKIPPED / RETRY_PENDING / EXHAUSTED
  → 释放首次档案 gate
  → 必要时刷新档案
```

### 5.2 首次档案时序

已确认“补全优先，失败降级”：

```text
第一尝试成功 / 无需补全
  → 释放 gate
  → 生成首次档案（读取新行业）

第一尝试发生技术失败
  → job=RETRY_PENDING
  → first_attempt_finished_at 有值
  → 释放 gate
  → 先生成无行业档案
  → 后续 retry 成功写行业
  → 再触发档案刷新
```

### 5.3 历史回填

```text
扫描 active plan 仍缺字段、且不存在同 plan job 的客户
  → purpose=HISTORICAL_BACKFILL
  → 同一 Workflow
  → 成功后触发 full profile refresh
```

历史 job 不阻塞已有档案读取，也不启用“首次档案 gate”。

## 6. 领域组件

### 6.1 `CustomerLifecyclePostCommitCoordinator`

客户第一次正式创建的统一提交后边界。职责：

- 构造/确保当前 plan 的 enrichment job；
- 登记现有客户智能 / Profile refresh 事件；
- commit 后 best-effort kick 两类 worker；
- 返回调度结果供日志使用，不把失败抛回客户保存接口。

支持两种接入：

1. **推荐的事务内登记**：客户已 flush 后，在 savepoint 中 ensure job；失败被隔离，客户事务继续。
2. **兼容的 after-commit ensure**：对已在内部 commit 的旧入口，用短会话补登记。

需要接入：

- `POST /v1/customers/`；
- 线索转客户的新旧命令分支；
- 旧 `/customers/ai/create/submit` 兼容入口；
- 未来正式客户导入 / 创建应用服务。

Agent 不单独接入：Agent 的 `create_customer` tool 最终调用 `POST /v1/customers/`。

不把事件登记下沉到裸 `customer_crud.create()`。CRUD 是数据写入原子，不应隐式启动模型任务；运行时入口必须经应用服务 / Coordinator。对遗漏入口由 reconciliation 修复。

### 6.2 `CustomerInitialEnrichmentWorkflow`

独立于 Profile Graph。第一期节点：

```text
load_customer
  → wait_for_settle_window
  → collect_missing_fields
  → load_field_catalogs
  → build_bounded_context
  → infer_fields
  → validate_decisions
  → apply_fields
  → finalize_job
```

可以用 LangGraph 表达并使用稳定 thread：

```text
customer-enrichment:{team_id}:{customer_id}:{plan_version}
```

checkpoint 只保存 JSON-safe 状态，不保存模型临时推理。

### 6.3 `CustomerEnrichmentFieldRegistry`

每个允许自动补全的字段必须注册 handler：

```text
field_key
is_missing(customer)
build_catalog(db, team_id)
normalize_and_validate(value, catalog)
audit_value(value)
```

禁止模型决定字段名；禁止处理未注册字段。字段 handler 不直接提交数据库；所有字段先完成校验，再由 `CustomerEnrichmentWriteService` 一次性条件写入，避免未来多字段逐个递增 version、产生部分写入。

第一期只注册：

```text
industry
```

未来字段各自定义写入规则；不能假设所有客户字段都适合自动写入。

### 6.4 `CustomerProfileReadinessGate`

Profile run 在获取执行 lease、递增 attempt 和标记档案 `UPDATING` **之前**检查：

```text
是否存在 purpose=INITIAL_CREATION
且当前 plan_version
且 first_attempt_finished_at IS NULL
且 now < profile_gate_deadline_at 的 enrichment job
```

- 不存在或 gate deadline 已到：正常执行档案；
- 存在：不 claim、不递增 attempt、不标记 `UPDATING`，把 profile run 的 `not_before_at` 持久化为 `min(profile_gate_deadline_at, now + short_delay)`；
- enrichment 第一尝试结束：清除该客户被延后 run 的 `not_before_at` 并 best-effort kick；
- enrichment worker 完全停摆时，`profile_gate_deadline_at` 到期后档案仍可降级生成，不会无限等待。

因此 `crm_customer_intelligence_runs` 需要新增 nullable `not_before_at`；`list_due` 和 `claim_for_execution` 都必须排除未来的 `not_before_at`，防止 direct kick 绕过 gate，也防止被阻塞的旧 run 占满每批 due 查询。

该 gate 对客户创建、首次活动等所有 profile 事件生效，避免 `customer_activity_created` 抢在补全前发布首次档案。

如果 enrichment job 因登记故障根本不存在，档案不阻塞；reconciliation 后续补 job，成功后再刷新档案。这是基础设施故障时的降级。

## 7. Durable Job 契约

新增表：`crm_customer_enrichment_jobs`。

```text
id
public_id                      # cej_...
team_id
customer_id
purpose                        # INITIAL_CREATION / HISTORICAL_BACKFILL
plan_version                   # customer-initial-v1
requested_fields_json          # ["industry"]
status                         # QUEUED/RUNNING/RETRY_PENDING/COMPLETED/SKIPPED/EXHAUSTED
available_at
profile_gate_deadline_at        # 仅 INITIAL_CREATION 使用
attempt_count
max_attempts
next_attempt_at
lease_token
lease_expires_at
run_id
graph_thread_id
first_attempt_finished_at
profile_gate_timed_out_at       # nullable；deadline 实际放行首次档案时首次写入，requeue 保留
profile_refresh_request_id
profile_refresh_enqueued_at
requeue_count
result_json
error_message
started_at
finished_at
created_time
updated_time
```

唯一键：

```text
(team_id, customer_id, plan_version)
```

`purpose` 是首次登记来源，不进入唯一键；同一 plan 不因 backfill 重复执行。

索引：

```text
(status, available_at, next_attempt_at, lease_expires_at, attempt_count, created_time)
(team_id, customer_id, plan_version)
```

状态语义：

- `QUEUED`：等待 settle window 或 worker；
- `RUNNING`：持有有效 lease；
- `RETRY_PENDING`：技术失败，等待下次执行；
- `COMPLETED`：至少一个字段成功写入，或模型正常返回并完成全部决策；
- `SKIPPED`：没有缺失字段、客户删除、目标字段已被用户填写、客户在模型期间变化；
- `EXHAUSTED`：技术失败达到最大次数。

默认配置：

```text
CUSTOMER_INITIAL_ENRICHMENT_SETTLE_SECONDS=5
CUSTOMER_INITIAL_ENRICHMENT_PROFILE_GATE_MAX_SECONDS=30
CUSTOMER_INITIAL_ENRICHMENT_MAX_ATTEMPTS=3
CUSTOMER_INITIAL_ENRICHMENT_LEASE_SECONDS=120
CUSTOMER_INITIAL_ENRICHMENT_RECOVERY_INTERVAL_SECONDS=60
CUSTOMER_INITIAL_ENRICHMENT_BATCH_SIZE=20
CUSTOMER_INITIAL_ENRICHMENT_BACKFILL_BATCH_SIZE=5
CUSTOMER_INITIAL_ENRICHMENT_BACKFILL_INTERVAL_SECONDS=300
CUSTOMER_INITIAL_ENRICHMENT_BACKFILL_ENABLED=true
```

重试退避：第一次失败后 60 秒、第二次失败后 300 秒，第三次失败转 `EXHAUSTED`。`profile_gate_deadline_at = available_at + PROFILE_GATE_MAX_SECONDS`；该 deadline 只控制档案是否等待，不终止 enrichment job。

## 8. Enrichment Plan 与模型合同

### 8.1 Plan 注册

第一期：

```text
plan_version = customer-initial-v1
fields = [industry]
backfill_enabled = true
```

新客户使用当前 active plan。未来字段变化必须升级 plan version，不原地改变已执行 plan 的语义。

新 plan 是否对历史客户执行，由 plan 的 `backfill_enabled` 明确决定。不得因部署新版本自动重跑所有客户。

### 8.2 一次模型调用

Workflow 先计算当前仍缺失的 requested fields；若为空，不调用模型。

输出采用字段决策列表，服务端只接受 requested set：

```json
{
  "decisions": [
    {
      "field": "industry",
      "value": "internet_saas",
      "reason": "客户从事软件研发并使用 AI Coding 产品"
    }
  ]
}
```

第一期 `industry` 必须返回一个 code；无业务依据时返回 `other`，不能省略。

不返回置信度；不保存 chain-of-thought。

## 9. 行业字段处理器

### 9.1 目录

执行时读取全部启用行业：

```text
一级 code + name
二级 code + name + parent code + parent name
```

模型只能输出目录内 code。

客户保存一个 code：

- 输出二级 code：展示时通过 parent 得到一级；
- 输出一级 code：表示只能确定大类；
- 无法判断：输出启用的一级 `other`。

若启用目录不存在一级 `other`，视为 `ENRICHMENT_CATALOG_INVALID` 技术 / 配置失败。该目录不变量必须在模型调用前验证，并在原子写入前再次验证；技术失败不写行业。

### 9.2 上下文

每次执行重新读取最新数据，不依赖创建请求里的瞬时 payload：

- 客户名称、城市、公司规模、来源；
- 已绑定产品名称；
- 主联系人职位；
- settle window 内已经落库的首次客户活动；
- 线索转化时可读取来源线索的基础描述 / 历史跟进（通过已有关系和客户上下文边界）。

最小化 PII：不把手机号、邮箱、联系人姓名发送给行业分类模型；联系人只提供职位。

活动数量和文本长度必须有界，例如最近 5 条、每条最多 500 字符。

### 9.3 校验

服务端验证：

- `field == industry` 且属于 requested fields；
- `value` 是当前启用行业 code；
- `reason` 非空、每字段最多 500 字符，只用于审计，并随操作日志和 job result 持久化；
- 一个字段最多一条 decision；
- 缺 decision、未知 field、非法 code、结构损坏均视为可重试执行失败。

### 9.4 条件写入

模型调用前读取 `expected_version`。写入必须经过专用 `CustomerEnrichmentWriteService`，不能使用当前无 team/version 保护的 `customer_crud.update_industry()`。

未来一个 plan 可能补多个字段：所有 requested decision 必须先完成闭世界校验，再在**同一个客户条件更新和同一个事务**中写入，Customer.version 只递增一次；任何 decision 无效时整批不写，任务进入重试，不允许半成功。

第一期条件写入等价于：按 `team_id + customer_id + expected_version` 定位客户，并要求 industry 仍满足字段 handler 的 missing 谓词（`NULL` 或 trim 后为空），然后一次写入 code、递增 version 并更新时间。不能把空白历史值当作已填写。

受影响行数：

- `1`：APPLIED；
- `0`：重新读取。行业已有值 → `SKIPPED/FIELD_ALREADY_FILLED`；客户仍存在、行业仍空但 version 已变化 → `RETRY_PENDING/CUSTOMER_CHANGED_DURING_ENRICHMENT`，用最新上下文重新执行，不使用旧判断，也不永久漏补。

写入事务中再次确认行业 code 仍为启用状态且启用目录仍存在一级 `other`，并记录一条操作日志：

```text
source = CUSTOMER_INITIAL_ENRICHMENT
plan_version
job_public_id
changed_fields
before / after
reasons = {field: bounded reason}
```

同一 `reasons` mapping 必须出现在 completed job 的 `result_json`；旧 result JSON 通过默认空 mapping 保持可读。

不需要在 Customer 表新增 `industry_source` 或置信度字段。

## 10. Settle Window 与首次活动竞态

Agent “创建客户 + 首次跟进”是两个顺序 command。客户创建事件可能早于首次活动提交，因此 job 默认延迟 5 秒执行，并在执行时重新读取最新上下文。

规则：

- `available_at` 之前不可 claim；
- `customer_activity_created` 到达时，如果 initial job 尚未首次执行，可以 best-effort 提前唤醒，但不是正确性的前提；
- 第一次执行读取当时所有已提交证据；
- job 完成后普通活动不再次触发初始补全；
- 如果首次活动最终晚于第一次补全，行业不会因后续活动自动重算，用户可编辑。未来若要支持持续纠偏，应设计独立能力，不扩张本期初始补全。

## 11. 档案刷新协调

### 11.1 首次尝试结束或 gate 超时

`first_attempt_finished_at` 在第一次真实执行结束时写入，包括：

- COMPLETED；
- SKIPPED；
- 第一次技术失败并转 RETRY_PENDING；
- 第一次即不可恢复 / EXHAUSTED。

不包括：尚未到 `available_at`、未拿到 lease、BUSY。

写入后释放 `CustomerProfileReadinessGate`，唤醒该客户被延后的 profile runs。

如果 worker 没有完成第一次执行，`profile_gate_deadline_at` 到期时 profile run 自行解除 gate并生成无行业档案；enrichment job 保持原状态，之后仍可执行。

实际 deadline 放行时，在同一事务中幂等写入 job 的 `profile_gate_timed_out_at`；只有 `INITIAL_CREATION` 且 `first_attempt_finished_at IS NULL` 的真实超时路径可写。reconciliation dry-run、历史任务、首次尝试已经结束的释放不写，后续 requeue 保留该时间戳作为 durable `profile_gate_timeout` 证据。

### 11.2 后续重试成功

如果第一次失败或 gate 超时后档案已经降级发布，后续补行业成功：

- 若存在尚未执行的创建期 profile run，清除其 `not_before_at` 并 kick；
- 否则登记一个客户主数据更新的 profile refresh；
- 更新事件 payload 标记 `change_origin=CUSTOMER_INITIAL_ENRICHMENT`；
- 该更新事件只刷新档案，不创建新的 enrichment job。

### 11.3 避免重复档案版本

`CustomerEnrichmentProfileCoordinator` 先查询是否存在被 gate 延后的 profile run：

- 有：只释放 / kick；
- 无：发布一次 customer-updated refresh。

成功登记后把 request id / 时间写入 job 的 `profile_refresh_request_id`、`profile_refresh_enqueued_at`。reconciliation 以这两个字段和真实 run 为证据补偿，不能只依赖 `result_json`。

不得无条件同时释放旧 run 和新增 refresh。

## 12. 失败策略

| 情况 | 结果 |
|---|---|
| 客户不存在 / 已删除 | SKIPPED |
| 请求字段都已有人工作值 | SKIPPED |
| 无 AI 配置 / API Key | RETRY_PENDING；第一次失败后释放档案 gate |
| 模型超时 / 网络错误 | RETRY_PENDING |
| structured output 无效 | RETRY_PENDING |
| 返回非法 / 停用行业 code | RETRY_PENDING |
| `other` 缺失或停用 | RETRY_PENDING / 最终 EXHAUSTED |
| 模型正常判断无法分类并返回 `other` | COMPLETED，写 `other` |
| 模型期间用户填写行业 | SKIPPED，不覆盖 |
| 模型期间客户其它字段变化、行业仍空 | RETRY_PENDING，用最新上下文重算 |
| profile gate 到期但 enrichment 未开始 | 档案降级运行；enrichment 保持待执行 |
| 重试耗尽 | EXHAUSTED；保留客户和已发布档案 |
| 档案刷新失败 | 不修改 enrichment 终态；沿用档案自身重试 |

客户删除由 context build 抛出 typed domain skip。job 直接进入 `SKIPPED/CUSTOMER_NOT_FOUND`，不进入模型、`RETRY_PENDING` 或 `EXHAUSTED`；首次尝试时间仍作为 lifecycle 证据写入，但已 deferred 的 Profile run 必须在同一 tenant/customer 范围内取消，不得释放/kick，也不得记录 profile refresh receipt。

`EXHAUSTED` 不自动无限重试。提供受权限保护的运维 requeue 能力：仅当 active plan 的目标字段仍缺失时，清空 lease/error、attempt_count 归零、`requeue_count + 1`、重新设为 QUEUED，并记录操作审计；唯一 job 不新建第二条。

## 13. 历史回填与数据迁移

### 13.1 Alembic


新增 migration 只负责：

- 创建 `crm_customer_enrichment_jobs`；
- 为 `crm_customer_intelligence_runs` 增加 nullable `not_before_at` 及 due 索引；
- 创建约束和索引；
- 不直接更新 `crm_customers.industry`；
- 不在 migration 中调用模型。

### 13.2 Backfill scheduler

新增独立 scheduler，不复用“缺档案”筛选：

```text
active plan backfill_enabled
AND plan 所需字段仍缺失（v1: Customer.industry 为 NULL 或仅空白字符）
AND 不存在 (team_id, customer_id, plan_version) job
```

`backfill_enabled=false` 时 backfill、preview 的 `would_schedule` 和 reconciliation 的历史 job 创建计数都必须为 0；reconciliation 仍可修复既有 job、gate 和 receipt。

按 `team_id, customer_id` 稳定排序 ensure job。新客户与历史回填使用同一执行服务但分开领取配额：高频 worker 每轮先处理 `INITIAL_CREATION`（默认 20），再至少处理一批 `HISTORICAL_BACKFILL`（默认 5）；不能只按全局优先级排序导致历史任务长期饥饿。

历史 purpose 不启用 profile gate；已有档案继续可读。补全成功后触发 full profile refresh。

### 13.3 Reconciliation 与运维恢复

定期修复：

- 新客户有创建事实但没有 active plan job；
- job RUNNING lease 过期；
- RETRY_PENDING 已到期；
- 客户已删除但 enrichment job 和 deferred Profile run 仍存在：reconciliation 额外扫描没有 Customer row、却存在 nonterminal `not_before_at` run 的 distinct tenant/customer orphan；正式运行 tenant-scoped 取消这些 run，dry-run 精确计数 `gates_cancelled`，不受普通 customer cursor 限制；
- enrichment 成功但 `profile_refresh_request_id` 为空，或 receipt 在同一 team/customer 下无法解析到 `released:<numeric_run_id>` / request ID 对应 run；过期 receipt 在同一 savepoint 内替换为实际释放的 run，或清空后登记新的 durable refresh；`CUSTOMER_NOT_FOUND` skip 不登记刷新；
- profile run 被 gate 延后但 first attempt 已结束或 gate deadline 已到；
- `not_before_at` 已到期但 run 未被 worker 领取。

对账结果把正常 gate 释放与删除客户取消分开：`gates_released` 只统计 release，`gates_cancelled` 按被取消 run 数统计。孤儿扫描只选择仍有 deferred nonterminal run 的 identity，避免干净孤儿占用 limit，并在每个 orphan savepoint 中隔离错误。普通客户和 orphan 使用独立 cursor：orphan identity 以该 `(team_id, customer_id)` 的最小 enrichment job id 为稳定 anchor，按 `min_job_id` 分页并返回 `next_orphan_job_id`；失败 identity 也推进 cursor。调用方分别携带 `after_customer_id` / `after_orphan_job_id`，独立迭代，直到两个 next cursor 都为 null。

重复 ensure 必须由唯一键变成 no-op。提供 diagnostics 与 EXHAUSTED requeue 服务 / 管理端 API，但不需要业务用户确认 UI。

### 13.4 Dry-run 与证据

```text
按团队的 industry missing（NULL 或仅空白）数量
已存在 job 数量
待创建 job 数量（active plan 禁止 backfill 时为 0）
已有非缺失 industry、应跳过数量
非缺失但不是有效启用 code 的历史值数量（仅报告，不自动覆盖）
行业目录是否存在启用的 other
```

运行证据至少记录：scheduled / applied / other / skipped / retry_pending / exhausted / requeued / profile_gate_timeout。

## 14. 所有创建入口的统一边界

支持的正式运行时创建入口不得直接把 `customer_crud.create()` 当完整应用动作。目标结构：

```text
CustomerCreationApplicationService
  → customer/contact source transaction
  → CustomerLifecyclePostCommitCoordinator
```

分阶段切换：

1. `POST /v1/customers/` 使用 Coordinator；Agent 自动覆盖。
2. 线索转客户的新旧分支使用 Coordinator。
3. 旧 AI submit 兼容入口改用 Coordinator，保留非权威 `industry_hint` parse/wire 字段，移除 `_match_industry()` 和同步行业写入；
4. 盘点 `CustomerService.create()`；无运行时 caller 则保留薄封装但标明调用者必须通过应用服务。
5. reconciliation 为漏发入口兜底。

创建 API 响应结构不因 enrichment 改变；可继续提示“客户档案正在后台整理”，但不承诺行业已经生成。

## 15. 可观测性与隐私

```text
plan_version
requested_fields
applied_fields
skipped_fields + reason
industry_code
reason（短文本）
industry_catalog_hash
model_name
first_attempt_outcome
profile_gate_outcome
profile_refresh_action
profile_refresh_request_id
requeue_count
```

不保存：

- 完整 prompt；
- chain-of-thought；
- 手机号、邮箱；
- 未截断的全部活动原文。

运行日志 / diagnostics 应能按 team、customer、status、purpose、plan_version 查询。

第一期不必在 Agent 对话中显示独立异步卡片。若未来需要，可把 job 投影到 `AgentAsyncOperation`；job 仍是唯一执行真相。

## 16. 未来字段复用规则

新增字段必须：

1. 注册独立 handler；
2. 声明 `is_missing` 和允许写入策略；
3. 定义闭世界目录或确定性校验；
4. 使用条件写，不能覆盖人工值；
5. 与同 plan 其它字段先全部校验，再一次原子写入、version 只增一次；
6. 升级 plan version；
7. 明确是否对历史客户 backfill；
8. 加入同一个模型 structured output，而不是新建一条模型任务。

不是所有字段都适合自动写入。例如负责人、状态、金额、商机阶段、合同信息、联系人身份关系属于强业务状态，禁止加入初始补全 plan。

## 17. 测试与验收

### 17.1 创建与异步隔离

- 客户 API 在模型不可用时仍返回 201，客户事实存在。
- 创建事务只登记 job，不调用模型。
- 重复创建事件只产生一个 `(team, customer, plan_version)` job。
- Agent 创建与页面创建进入同一 job。
- 线索转客户进入同一 job，且来源线索上下文可读取。

- 行业为空 + 明确二级行业 → 写二级 code。
- 只能判断一级 → 写一级 code。
- 业务无法判断 → 写 `other`。
- 模型超时 / 无配置 → 不写 `other`，进入 RETRY_PENDING。
- 非目录 code → 重试，不写入。
- `other` 停用 → 不写入。
- 行业已有值 → 不调用模型或 SKIPPED，绝不覆盖。
- 模型期间用户填写行业 → 条件更新 0 行，SKIPPED。
- 模型期间客户其它字段变化、行业仍空 → RETRY_PENDING，使用最新上下文重算。
- 未来多字段 plan 中任一 decision 无效 → 全部不写；全部有效时一次事务写入、version 只加一。

### 17.3 档案 gate

- available_at / first attempt 前的 customer-created、activity-created profile run 被持久化延后，且不消耗模型 attempt、不标记档案 UPDATING。
- direct kick 也会经过 gate，不能绕过 `not_before_at`。
- 第一次补全成功后，首次档案读取新行业。
- 第一次技术失败后，无行业档案仍能发布。
- enrichment worker 未运行时，gate deadline 到期后无行业档案仍能发布。
- 后续补全成功后，档案刷新一次。
- 不同时“释放旧 profile run + 新建重复 refresh”。

### 17.4 恢复与幂等

- lease 未过期不能重复 claim。
- lease 过期可恢复。
- `available_at` / `not_before_at` 未到期不能 claim。
- RETRY_PENDING 到期可重试。
- 达到 3 次后 EXHAUSTED。
- EXHAUSTED 可通过运维 requeue 原 job，不新增重复行。
- 服务重启不丢任务。
- reconciliation 能补登记缺失 job、释放过期 gate、补档案 refresh。

### 17.5 历史回填

- 只扫描 plan 仍缺字段且没有 job 的客户。
- 已有行业客户不进入模型。
- 已有档案但行业为空的客户仍进入 backfill。
- 非空但非法 / 停用行业只进入 dry-run 报告，不自动覆盖。
- 重跑 scheduler 不新增重复 job。
- 初始客户任务优先，但每轮仍保留 backfill 配额，历史任务不饥饿。
- 回填期间旧档案继续可读。

## 18. 风险与控制

- **行业 `other` 比例过高。** 这是可编辑字段，不阻断上线；通过 job 统计观察，并迭代 prompt / 行业目录。
- **5 秒不足以等到首次活动。** 该值配置化；执行时读最新数据。后续活动不自动重算，属于本期“只在首次阶段运行”的明确代价。
- **补全 worker 停摆。** profile gate 有独立 deadline；档案最多延后固定时间，不无限等待。
- **目录粒度不覆盖真实客户。** 模型只能选现有目录；先完善目录，不允许自由文本落库。
- **创建入口漏发。** 唯一 job + reconciliation 修复。
- **任务注册失败导致档案抢跑。** 无 job 时档案允许降级运行；reconciliation 后补全成功再刷新。
- **未来 plan version 误触发历史重跑。** 每个 plan 必须显式声明 `backfill_enabled`，不得默认全量执行。
- **自动写入引发事件循环。** 只有创建 Coordinator 创建 enrichment job；普通 customer-updated 事件只刷新档案。
- **新客户长期压住历史回填。** 初始与 backfill 分开领取配额。
- **模型成本。** 每客户每 plan 最多一个 job；一次调用补全部缺失字段；已有值不调用。

## 19. 合并门禁

一次发布必须同时具备：

1. durable job 表、租约、重试、运维 requeue 和恢复 worker；
2. 创建 post-commit Coordinator 及入口切换；
3. `customer-initial-v1` + industry handler + 闭世界校验；
4. 多字段可扩展的一次模型调用、全量校验和原子条件写入；
5. first-attempt profile gate、持久 `not_before_at`、gate deadline 与失败降级；
6. 独立历史空行业 backfill及公平领取配额；
7. reconciliation 和 profile refresh receipt；
8. 上述创建、竞态、失败、恢复、requeue 和回填验收测试。

不允许只接新客户而不处理历史漏数，也不允许只写 industry 而没有 gate / 重试 / 幂等。
