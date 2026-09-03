# 客户活动 Agent Workflow Parity 实施规格

- **确认日期：**2026-09-02
- **状态：**产品规则已冻结，实施中（T11-T18 代码与专项回归已完成；T19 代码闭环已接入，真实联调待完成；T20 migration 122 与 SQLite 行为测试已完成，真实数据库 dry-run 待完成；T21 待完成）
- **权威性：**本文是本轮“旧 Agent 跟进流程迁移到新 Workflow”工作的实施权威文档。后续实现、评审和验收以本文为准，不再重复询问已经冻结的产品规则。
- **差异来源：**[旧流程到新 Workflow Parity Matrix](./legacy-workflow-parity-matrix.md)
- **确认过程：**[Parity 待确认事项分析](./workflow-parity-open-questions.md)
- **验收用例：**[客户活动 Workflow 验收矩阵](./customer-activity-workflow-acceptance-matrix.md)
- **代码状态：**以[实施状态页](./customer-activity-workflow-implementation-status.md)为准；本文只定义目标合同和发布阻断条件。

## 1. 目标

本次不是单独补回一个“跟进评分”节点，而是完整恢复并重构客户活动链路：

```text
语义理解
→ 客户解析与跨轮绑定
→ 内容整理
→ 质量评分
→ 下一步行动门禁
→ 必要时单问题补充
→ 一次性最终写入
→ 独立后台后处理
→ 独立商机建议与操作
```

目标同时解决：

- Agent 评分后写入又被后台重复整理和评分；
- 页面表单依赖 `asyncio.create_task()`，任务可能丢失；
- PostCommitJob 在活动最终化前过早创建；
- 旧 `/process`、`/evaluate`、活动修改和同步模式形成双轨；
- 商机建议与跟进记录混成一个工作流；
- 删除、重试、部署中断时缺少一致幂等语义；
- 旧流程中的质量、下一步行动、业务建议和跨轮恢复能力未完整迁移。

## 2. 本期范围

### 2.1 纳入范围

- 客户下新增跟进记录；
- 客户下新增会议纪要；
- 删除跟进记录或会议纪要；
- Agent 跟进完成后的商机建议；
- 用户确认后的商机创建；
- 用户明确要求时的商机阶段推进；
- 页面表单活动的异步整理、评分和现有后台任务；
- 客户创建与首次活动的部分成功和独立重试；
- 旧活动执行链路向 durable job 的一次性切换。

### 2.2 不纳入范围

- 创建线索；
- 回款记录、回款计划；
- 合同、License、发票、部署信息等建议或动作；
- 跟进记录和会议纪要修改；
- 对全部历史活动重新整理或重新评分；
- 恢复旧 Agent graph/runtime 作为 fallback；
- 长期保留新旧评分或新旧后台任务双轨。

## 3. 冻结的领域规则

### 3.1 活动操作

客户活动只有：

```text
新增
删除
```

不存在修改操作。删除沿用现有业务删除机制，不新增“删除评分”。

### 3.2 业务原子性

以下均为独立原子：

```text
创建客户
创建跟进记录
创建会议纪要
创建商机
推进商机阶段
```

一个原子成功后不因为另一个原子失败而回滚。尤其是：

- 客户创建成功、首次活动失败：保留客户；
- 跟进成功、商机建议失败：保留跟进；
- 跟进成功、商机创建失败：保留跟进；
- 用户取消商机创建：不影响跟进；
- PostCommit 或客户智能刷新失败：不影响活动事实。

### 3.3 活动内容和类型

- `source_content` 保存用户原始输入；多轮补充时追加用户后续补充原文；
- 不把 Agent 问题、系统提示、评分理由、模型推理或规范化稿写入 `source_content`；
- 最终整理稿、摘要和结构化字段使用各自 canonical 字段；
- evaluator 评分的内容必须与最终落库的整理内容一致；
- `activity_kind` 是客户活动唯一 canonical 字段；新客户活动运行时不保存、不查询旧 `method`。
- 旧线索表仍由线索子系统使用时，只允许在 `LeadFollowUp.method → activity_kind` 的一次性历史边界适配器中读取；该适配器不得进入客户活动运行时主链路，也不构成长期双轨。

### 3.4 最终评分

- Agent 与页面表单复用同一套 canonical rubric/evaluator；
- 通过阈值固定为 `score >= 60`；
- 只保存最终评分，不保存同一活动的评分历史、中间分数或尝试过程；
- Agent 补充前的低分不落业务表；
- 页面低分是有效评分结果，不是技术失败；
- Agent evaluator 失败、超时、非法输出时 fail-closed，不写活动；
- 页面 evaluator 失败时保留原始活动，由 durable job 重试。

### 3.5 下一步行动门禁

Agent 活动即使评分通过，也必须单独判断下一步行动：

- 没有下一步行动：追问；
- “继续跟进”“再看看”“保持联系”等模糊表达：追问；
- 明确动作但没有时间：允许保存，不猜日期；
- 明确动作且有时间：沿用现有时间解析和任务投影；
- 明确暂无下一步：允许保存，但保留原因或复查条件。

页面表单路径不进行同步交互补充；AI 只保存最终评估结果。

### 3.6 低质量交互

Agent 评分低于 60 时：

```text
不创建活动
不创建 PostCommitJob
不创建商机建议
只问一个最关键补充问题
```

用户补充后必须合并完整用户语义，重新执行：

```text
语义解析
→ 内容整理
→ 质量评分
→ 下一步行动判断
```

不得只评分用户最后一句补充。

### 3.7 历史待办确认与延期操作边界

历史待办确认是一个轻量的“完成状态确认”交互，只回答这项待办是否已经完成：

- 新建确认 Case 统一使用“现在完成了吗?”文案；
- Agent UI 和兼容确认渠道只展示“已完成”“先放着”“不管了”三个选项；
- “先放着”和无法判断的非完成回复都不得修改待办时间或状态；
- 延期是独立的 `transition_follow_up_task` 操作，不作为历史待办确认的选项或追问；
- 已存在的旧 Case、投影消息和投递快照不做破坏性数据清洗，在读取边界统一转换旧的“需要延期吗?”/“不需要继续跟进了吗?”文案；
- 旧数据原始字段仍保留，避免历史数据迁移影响 dev 环境和审计证据。

## 4. 客户解析、记忆和创建

### 4.1 客户解析顺序

首次处理：

```text
语义解析
→ Customer Resolver
→ 服务端权限/存在性校验
→ customer_id 写入 Workflow checkpoint
```

补充轮次：

```text
复用 checkpoint.customer_id
→ 重新做权限和存在性校验
→ 不重新搜索客户
→ 不重复询问客户
```

只有用户明确切换客户时才清除：

- `customer_id`；
- 旧客户业务上下文；
- 旧客户商机候选。

活动正文继续保留并对新客户重新判断。

### 4.2 客户未匹配

找不到客户时直接说明没有匹配客户。不得自动询问是否创建客户，也不得进入创建线索流程。

### 4.3 客户创建

只有用户明确要求创建客户且必填信息完整时调用客户创建 API：

- 重复客户由 API 负责最终保护；
- API 返回唯一已有客户时直接复用；
- API 返回多个候选时才让用户选择；
- 不创建线索；
- 客户创建和首次活动使用独立 command、独立幂等键。

### 4.4 部分成功

客户创建成功、活动创建失败时返回显式部分成功：

```json
{
  "status": "FAILED",
  "code": "WORKFLOW_PARTIAL_SUCCESS",
  "partial_success": true,
  "completed_commands": [
    {
      "command_id": "create_customer",
      "status": "COMPLETED",
      "result": {"customer_id": "cus_xxx"}
    }
  ],
  "failed_command_id": "create_customer_activity",
  "partial_result": {
    "customer_id": "cus_xxx",
    "activity_created": false
  }
}
```

重试时只执行尚未成功的活动 command。

## 5. 目标架构

```text
Agent Workflow
    ├── Customer Resolver
    ├── Canonical Activity Structurer
    ├── Canonical Activity Evaluator
    ├── Next Action Gate
    ├── Workflow checkpoint / interaction
    └── create_final_from_agent()

页面活动 API
    └── create_pending_from_form()
            └── CustomerActivityAIJob
                    └── structure + evaluate
                            └── finalize_pending_from_ai()

活动最终化
    ├── CustomerActivityPostCommitJob
    ├── CustomerIntelligenceRefresh
    └── Agent 来源时的 CustomerOpportunitySuggestionJob

用户确认新商机
    └── 独立 CreateOpportunity Workflow

用户明确推进商机
    └── 独立 MoveOpportunityStage Workflow
```

这些流程共享领域合同，但不共享业务事务。

## 6. CustomerActivityWriteService 深化

不新增一层只做转发的 `CustomerActivityFinalizer`。直接将现有 `CustomerActivityWriteService` 深化为唯一活动写入边界。

### 6.1 `create_pending_from_form()`

事务内：

```text
创建原始活动
写 processing_status=PENDING
写 effectiveness_status=PENDING
创建 CustomerActivityAIJob
提交
```

不得创建：

```text
PostCommitJob
OpportunitySuggestionJob
```

提交后可以 kick worker，但正确性依赖 recovery scheduler，不依赖进程内 task。

### 6.2 `create_final_from_agent()`

事务内一次性：

```text
创建活动
写最终整理内容
写最终摘要/下一步行动/时间
写最终评分、原因和分项
写 processing_status=COMPLETED
写 effectiveness_status=COMPLETED
创建 PostCommitJob
创建/登记客户智能刷新工作
写 Agent command 幂等结果
提交
```

不得：

```text
创建 CustomerActivityAIJob
调用 trigger_processing()
调用 trigger_evaluation()
```

Agent 来源且符合商机建议条件时，商机建议任务必须独立登记；其调度失败不能回滚活动。

### 6.3 `finalize_pending_from_ai()`

AI Workflow 只返回计算结果，由本入口在一个事务中：

```text
校验活动存在且未删除
校验 activity_revision
写最终整理内容
写最终评分
两个活动状态置 COMPLETED
增加最终化 revision
创建 PostCommitJob
登记客户智能刷新
标记 AIJob COMPLETED
提交
```

禁止先提交整理结果、再提交评分结果。

## 7. 两条活动路径

### 7.1 Agent 路径

```text
用户输入
→ 语义解析
→ 客户解析/复用
→ 内容整理
→ 评分
→ score < 60：单问题补充，不写入
→ score >= 60：下一步行动门禁
→ 门禁不通过：补充，不写入
→ 门禁通过：create_final_from_agent()
→ 返回活动成功
→ 独立生成商机建议
```

最终状态直接为：

```text
processing_status=COMPLETED
effectiveness_status=COMPLETED
```

### 7.2 页面表单路径

```text
页面提交
→ 保存原始活动
→ 创建 durable AIJob
→ 立即返回
→ Worker 整理和评分
→ finalize_pending_from_ai()
→ 创建 PostCommitJob
```

页面即使低分：

```text
活动保留
最终评分保留
状态为 COMPLETED
PostCommit 继续执行
不生成商机建议
```

页面 AI 技术失败：

```text
活动保留
任务自动重试
重试耗尽后活动投影为 FAILED
```

### 7.3 跟进记录和会议纪要

两类活动共用以上写入、AIJob、评分和后台任务框架，不建立两套实现。

## 8. 状态模型

### 8.1 活动状态是 UI 投影

不新增第三套 `workflow_status`。沿用：

| 场景 | processing_status | effectiveness_status |
|---|---|---|
| 页面刚保存 | `PENDING` | `PENDING` |
| AIJob 正在执行 | `PROCESSING` | `GENERATING` |
| 整理评分成功，包括低分 | `COMPLETED` | `COMPLETED` |
| AIJob 重试耗尽 | `FAILED` | `FAILED` |
| Agent 最终写入 | `COMPLETED` | `COMPLETED` |

活动状态不是后台任务唯一事实来源，任务表才负责 lease、重试和终态。

### 8.2 CustomerActivityAIJob

推荐状态：

```text
QUEUED
RUNNING
RETRY_PENDING
COMPLETED
SKIPPED
EXHAUSTED
```

终态：

```text
COMPLETED
SKIPPED
EXHAUSTED
```

推荐字段：

```text
public_id
team_id
activity_id
activity_revision
job_type
submission_source
status
attempt_count
next_attempt_at
lease_token
lease_expires_at
run_id
result_json
error_message
created_time
started_at
finished_at
updated_time
```

`submission_source` 只允许：

```text
FORM
CUTOVER_MIGRATION
```

出现 `AGENT` 即表示 Agent 又进入重复评分路径。

### 8.3 PostCommitJob

继续使用 durable 状态和 lease 模型。活动删除后任务记录必须保留并转为 `SKIPPED`，因此移除 `activity_id` 的 `ondelete="CASCADE"`；不得使用 `SET NULL` 丢失原始活动 ID。

### 8.4 商机建议任务

独立于 PostCommitJob 和客户智能任务。其失败、重试或耗尽不修改活动状态。

## 9. 幂等与并发

### 9.1 AIJob 唯一性

数据库唯一约束至少覆盖：

```text
team_id + activity_id + activity_revision + job_type
```

不能仅使用“先查再插”的应用层判断。

### 9.2 Agent command 幂等

Agent 最终写入使用：

```text
workflow_run_id + command_id
```

相同 command 重放时返回原 `activity_id` 和原结果，不重新创建活动、评分或下游任务。

### 9.3 页面提交幂等

前端每个表单会话提供稳定 `submission_id`。相同用户、团队和 `submission_id` 重试时返回原活动和 AIJob；重新打开新表单使用新 ID。

### 9.4 Worker lease

Worker 必须原子 claim，并在完成/失败写入时验证自己的 `lease_token`。进程崩溃后由 lease 过期和 recovery scheduler 接管。

### 9.5 删除竞态

Worker 开始前和最终提交事务内均检查活动存在性。LLM 执行期间活动被删除时：

```text
不写最终内容
不写评分
不创建 PostCommitJob
AIJob → SKIPPED
```

### 9.6 revision 冲突

任务绑定旧 revision 时不得覆盖新状态。活动无修改入口，但 revision 仍用于防止部署重放、旧任务和异常脚本覆盖。

## 10. 后台任务边界

最终活动事实成功后，下游关系为：

```text
CustomerActivity finalized
├── CustomerActivityPostCommitJob
├── CustomerIntelligenceRefresh
└── CustomerOpportunitySuggestionJob（仅 Agent 合格活动）
```

三者独立执行，不互相等待，不共同回滚。

所谓后台任务必须立即返回；如果请求需要等待任务完成，就不属于本方案中的后台任务。

## 11. 商机流程

### 11.1 建议生成

Agent 活动成功后独立生成商机建议。建议任务不直接创建商机。

触发条件：

```text
Agent 来源
活动成功最终化
score >= 60
下一步行动门禁通过
活动类型允许分析商机
```

页面活动本期不生成商机建议。

### 11.2 已有商机

LLM 和业务数据高置信度匹配已有商机时：

```text
判定已有商机
忽略重复创建
不强制用户确认
不自动推进阶段
```

不展示僵硬的“使用已有/继续新建/取消”。低置信度或证据冲突时不自动创建，也不强迫用户选择。

### 11.3 明确新商机

```text
跟进先保存
→ Agent 输出“是否帮你创建商机？”
→ Agent UI 是/否组件
→ 点击“是”
→ Agent 页面内嵌表单
→ 提交或取消
→ 独立 CreateOpportunity Workflow
```

弃用旧重型弹窗。

### 11.4 商机推进

仅当用户明确要求推进时启动独立 `MoveOpportunityStage` Workflow。描述“已进入某阶段”不等于授权系统修改阶段。

提交时状态已变化：

```json
{
  "success": true,
  "status": "SKIPPED",
  "skip_reason": "OPPORTUNITY_STATE_CHANGED"
}
```

静默跳过，不覆盖、不重试、不提示用户。

## 12. 删除语义

活动被删除后：

```text
CustomerActivityAIJob → SKIPPED
CustomerActivityPostCommitJob → SKIPPED
CustomerOpportunitySuggestionJob → SKIPPED
```

统一原因：

```text
SOURCE_ACTIVITY_DELETED
```

不得：

- 反复重试；
- 写回活动；
- 重新创建活动；
- 继续创建商机；
- 依赖数据库级联把任务证据直接删除。

## 13. 旧入口清理

同一目标版本内删除生产路径：

```text
PUT /v1/customer-activities/{activity_id}
PATCH /v1/customer-activities/{activity_id}/next-time
POST /v1/customer-activities/{activity_id}/process
POST /v1/customer-activities/{activity_id}/evaluate
post_commit_mode=sync
trigger_processing()
trigger_evaluation()
```

不得用 forwarding wrapper 将旧入口悄悄转发到新流程。旧客户端命中已删除接口时返回 404/405；页面创建接口只代表 `create_pending_from_form()`，Agent 不再调用普通页面活动 API 后触发异步评分。

## 14. 上线切换

采用一次性硬切换，不做新旧 Workflow 并行执行。

### 14.1 切换顺序

```text
1. 构建并验证目标制品
2. 静态检查旧入口为零
3. 停止 Web/IM Agent、API、worker 和相关 scheduler
4. 记录 cutover watermark
5. 完成数据库备份及恢复演练
6. 执行 Alembic 结构迁移
7. 执行一次性未完成活动/任务迁移
8. 验证迁移计数和唯一性
9. 启动新服务和 durable recovery scheduler
10. 执行真实 HTTP/Workflow/Worker 验收
11. 验收通过后开放流量
12. 观察窗口后删除一次性迁移设施
```

### 14.2 历史活动处理

已完成历史活动：

```text
不重新整理
不重新评分
不补 AIJob
```

切换时真正未完成的活动：

```text
PENDING / PROCESSING / GENERATING
→ 创建一条 CUTOVER_MIGRATION AIJob
→ 由新流程接管
```

旧 `PROCESSING/GENERATING` 不恢复进程内 task，也不恢复旧 AI graph checkpoint。

### 14.3 旧 PostCommitJob

- 活动已最终化：保留未完成任务，由新 executor 按 lease 和幂等恢复；
- 活动尚未最终化但已提前创建：标记 `SKIPPED/REPLACED_BY_ACTIVITY_AI_JOB`；
- 新 AI 最终化时增加 revision，并为最终 revision 创建 canonical PostCommitJob；
- 活动已删除：标记 `SKIPPED/SOURCE_ACTIVITY_DELETED`。

### 14.4 回滚边界

正式放流前验收失败：

```text
停止新服务
恢复数据库备份
恢复上一完整应用版本
```

正式放流且产生新格式业务写入后：

```text
不允许直接启动旧 Runtime
默认只做前向修复
```

如必须回退，需停流并使用完整备份/PITR，明确接受恢复点之后的数据影响。

## 15. 运行一致性与可观测性

至少监控：

```text
AIJob queued/running/retry_pending/exhausted 数量
最老 queued 任务年龄
AIJob 执行耗时和跳过原因
Agent 活动却存在 AIJob
页面 PENDING 活动却没有 AIJob
AIJob COMPLETED 但活动未完成
活动最终化但没有 PostCommitJob
同一 revision 多任务
活动删除后任务仍在重试
```

对账服务可幂等修复：

- 页面 PENDING 活动缺 AIJob；
- 已最终化活动缺 PostCommitJob；
- 删除活动仍有可执行任务。

如果 AIJob 已 `COMPLETED` 但活动没有最终结果，应作为事务不变量破坏告警，不能静默重新评分。

## 16. 前端合同

- 活动列表和详情继续使用现有展示方式；
- 用户不看到 lease、attempt_count、Job ID 等内部信息；
- 低质量交互一次只展示一个补充问题；
- 商机建议使用现有 Agent UI 是/否组件；
- 点击“是”后展示 Agent 页面内嵌表单，支持提交和取消；
- 刷新页面后恢复客户选择、质量补充、商机确认或商机表单状态；
- 所有确认、提交、取消操作均防止重复点击和重复 resume。

## 17. 关键系统不变量

1. Agent 最终活动永远不创建 CustomerActivityAIJob。
2. 页面活动永远通过 CustomerActivityAIJob 整理和评分。
3. 一条活动只保存一个最终评分。
4. AI 中间整理或评分结果不分步写入活动。
5. PostCommitJob 只在活动最终化后创建。
6. 页面低分不是技术失败，活动保留且 PostCommit 继续。
7. 商机建议、创建或推进失败不影响活动。
8. 活动删除后所有相关后台任务静默 `SKIPPED`。
9. Worker 重试不重复创建活动、评分或业务副作用。
10. Workflow resume 不重复执行已完成 command。
11. 客户只在首次解析或明确切换时搜索；resume 仍重新校验权限和存在性。
12. 不创建线索，不把回款、合同等范围外动作带入本期。

## 18. 实施 Tickets

### T11：统一活动数据契约和状态定义

- 明确原文、最终整理稿、评分和 provenance；
- 定义页面/Agent submission source；
- 定义 AIJob、PostCommitJob 和 suggestion job 状态；
- 添加唯一键、revision 和幂等合同。

完成定义：schema、migration、contract tests 通过。

### T12：深化 CustomerActivityWriteService

新增：

```text
create_pending_from_form()
create_final_from_agent()
finalize_pending_from_ai()
```

完成定义：三入口事务测试通过，旧通用写法不再被活动创建路径调用。

### T13：新增 CustomerActivityAIJob durable 任务

建议新增：

```text
app/models/customer_activity_ai_job.py
app/crud/customer_activity_ai_job.py
app/services/customer_activity_ai_job_service.py
app/tasks/customer_activity_ai_job_recovery.py
migrations/versions/119_customer_activity_ai_jobs.py
```

完成定义：enqueue、claim、lease、retry、restart、skip、exhausted 全部可验证。

### T14：AI Workflow 计算与写入分离

删除图中的分步持久化节点，只返回最终计算结果；由写入服务一次性最终化。

完成定义：不存在“内容已提交但评分未提交”的状态。

### T15：Agent Workflow 接入质量和行动门禁

- canonical structurer/evaluator；
- 60 分门禁；
- 单问题补充；
- 下一步行动门禁；
- customer_id checkpoint 复用；
- Agent 最终写入。

完成定义：Agent 路径无 AIJob、无重复评分、可 resume。

### T16：页面表单接入 AIJob

跟进记录和会议纪要页面统一接入 `create_pending_from_form()`。

完成定义：请求立即返回、任务 durable、低分保留、失败重试。

### T17：收拢 PostCommit、删除和跳过逻辑

- PostCommit 延后到最终化；
- 移除活动外键级联；
- 三类后台任务统一删除检查；
- revision 和幂等恢复。

### T18：清理旧入口和双轨

删除活动修改、手工 process/evaluate、同步模式、`trigger_processing()`、`trigger_evaluation()` 及不再使用的服务和测试。

### T19：商机建议与商机 Workflow

- 独立 suggestion job；
- 高置信度已有商机静默忽略；
- 是/否组件；
- Agent 内嵌表单；
- 独立创建/推进 Workflow；
- 状态变化静默跳过。

### T20：一次性数据迁移

迁移文件：`CRM-Server/migrations/versions/122_customer_activity_cutover.py`。T20 不是重新处理全部历史活动，而是把切换时仍未完成的事实安全交给 canonical durable pipeline。

- 第一次运行生成固定 `cutover_watermark`，后续重跑使用同一 watermark；
- 只接管 watermark 之前处理状态为 `PENDING`/`PROCESSING`，或评分状态为 `PENDING`/`GENERATING` 的活动；
- 已完成历史活动的原始内容、整理稿和最终评分保持不变，不重新评分、不创建 AIJob；
- 未完成活动按 `team_id + activity_id + activity_revision + job_type` 至多创建一条 `CUTOVER_MIGRATION` AIJob；
- 未完成的历史 Agent 活动在切换边界重分类为 `CUTOVER_MIGRATION`，由 canonical finalization gate 接管，避免旧 Agent 路径和新 AIJob 双重评分；
- 未完成活动对应的旧 PostCommitJob 标记为 `SKIPPED/REPLACED_BY_ACTIVITY_AI_JOB`；已最终化活动的旧 PostCommitJob 保留并由新 executor 恢复；
- 活动已经删除但任务行仍存在时，任务标记为 `SKIPPED/SOURCE_ACTIVITY_DELETED`，保留结果和错误证据；
- 不恢复旧进程内 task 或旧 Agent graph/checkpoint；
- 证据写入 `crm_customer_activity_cutover_runs`，至少包括运行键、watermark、状态、接管/跳过/替代/保留计数；
- 固定运行键已完成后再次执行是 no-op，只返回既有证据，不重复扫描和计数；中断后若证据仍为 `RUNNING`，可按自然唯一键继续。

旧 `method` 不作为客户活动运行时字段迁移保留。线索历史转换只在 `CustomerActivityCRUD.migrate_from_lead()` 的边界适配器完成；真实发布后客户活动主链路不得重新引入旧映射读取。

### T21：全链路验收和上线切换

执行验收矩阵、真实模型 golden cases、Worker 重启、迁移重跑、备份恢复和放流门禁。

### 依赖顺序

```text
T11
→ T12
→ T13 + T14
→ T15 + T16
→ T17 + T18
→ T19
→ T20
→ T21
```

## 19. 主要代码落点

Workflow：

```text
CRM-Server/app/services/agent/workflow/planning.py
CRM-Server/app/services/agent/workflow/contracts.py
CRM-Server/app/services/agent/workflow/execution.py
CRM-Server/app/services/agent/tools/service.py
CRM-Server/app/services/agent/tool_registry.py
```

活动：

```text
CRM-Server/app/services/customer_activity_write_service.py
CRM-Server/app/services/customer_activity_ai/workflow.py
CRM-Server/app/services/customer_activity_ai/evaluation_agent.py
CRM-Server/app/services/agent/quality.py
CRM-Server/app/services/customer_activity_processing_service.py
CRM-Server/app/api/customer_activities.py
CRM-Server/app/crud/customer_activity.py
CRM-Server/app/schemas/customer_activity.py
```

后台任务：

```text
CRM-Server/app/models/customer_activity_post_commit_job.py
CRM-Server/app/crud/customer_activity_post_commit_job.py
CRM-Server/app/services/customer_activity_post_commit_job_service.py
CRM-Server/app/services/customer_activity_post_commit_workflow.py
```

部署与迁移：

```text
CRM-Docs/deployment/README.md
CRM-Docs/deployment/deploy.sh
CRM-Server/migrations/versions/
CRM-Server/scripts/
```

## 20. 当前代码已知差距

截至 2026-09-02，T11-T18 的代码与专项回归已完成；T19 的代码闭环已接入但真实联调待完成；T20 migration 122、证据模型和 SQLite 行为测试已完成，但真实数据库升级与发布演练仍未完成；以下仍是待实施或待验收事实：

- T15 仍需真实模型 Golden Cases 和完整部署环境下的 resume/多轮重解析验收；
- T19 仍需真实 CRM API、Worker、Agent UI 联调，以及 MOVE stale、重复点击和安全 replay 的全链路验收；
- T20 仍需真实 `alembic upgrade head`、生产 dry-run、备份恢复、worker 重启和中断重跑演练；本地 Alembic 当前数据库停留在 revision 117，不能把 `alembic check` 通过误认为真实升级已完成；
- T21 全链路验收、真实模型 Golden Cases、部署 readiness 和最终 code review 尚未完成。

T17 删除任务证据已经落地：migration 120 移除 PostCommitJob 级联外键；删除活动时未完成 AIJob/PostCommitJob 在同一事务内标记为 `SKIPPED`，原因统一为 `SOURCE_ACTIVITY_DELETED`，并保留任务结果和删除前错误证据。相关定向测试已通过。

## 21. 发布阻断条件

以下任一存在即不得上线：

- Agent 活动写入后仍创建 AIJob 或调用旧处理入口；
- 低于 60 或缺下一步行动仍能写入；
- 页面保存时提前创建 PostCommitJob；
- AI 仍分两次持久化内容和评分；
- 相同 command、submission 或 job 可以产生重复记录；
- 删除活动后任务仍重试或被级联删除；
- 商机失败会回滚跟进；
- 旧活动修改、process/evaluate 或 sync 入口仍可用；
- Worker 重启或迁移重跑产生重复副作用；
- 需要恢复旧 Runtime 才能完成新流程。

## 22. 文档维护规则

- 已确认产品规则只在本文修改，不在实现过程中口头漂移；
- parity matrix 保留作为差异证据，不作为最终合同；
- open questions 保留确认过程，但已冻结项不得重新询问；
- 测试用例统一维护在 acceptance matrix；
- 代码实现改变本文不变量时，必须先更新本文并说明决策原因；
- 本文定义目标合同；各 Ticket 的完成状态以[实施状态页](./customer-activity-workflow-implementation-status.md)、测试和真实上线证据为准。
