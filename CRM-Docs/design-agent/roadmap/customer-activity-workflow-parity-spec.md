# 客户活动实施规格

- **确认日期：**2026-09-02
- **权威性：**本文定义客户活动、页面表单、AIJob 和删除语义；销售助手写命令的幂等与恢复见[销售助手命令契约](../runtime/assistant-command-contract.md)，领域决策见 [ADR 0001](../../../docs/adr/0001-customer-activity-workflow-parity.md)。旧 Agent 已按 [ADR 0003](../../../docs/adr/0003-legacy-agent-entry-retirement.md) 停止接收新输入。

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

旧 Agent 补充后重新解析完整用户语义；销售助手按 ADR 0001 §7 局部合并补充或修订，再对完整最终稿重新整理、评分和判断下一步。旧路径顺序如下：

```text
语义解析
→ 内容整理
→ 质量评分
→ 下一步行动判断
```

不得只评分用户最后一句补充。

### 3.6.1 旧 Agent 已受理任务：缺失跟进内容时取消

仅 `provide_follow_up_content` 的补充内容交互可在“继续”旁提供“取消”；取消不受必填正文校验限制。服务端签发的 Action 同时授权取消，提交值固定为 `{"cancel": true}`；不允许客户端自行加入或扩展取消许可。确认卡片、历史待办和商机建议保留原有语义。

成功取消必须经原 Workflow checkpoint 的拒绝续接终结当前工作流，不写入本次跟进，也不创建其后处理或商机建议。Action 在服务端持久化独立的 `CANCELLED` 终态和对应结果消息；同一请求可重放原结果，不同请求的取消/继续竞争以最先取得并完成的 Action 为准。历史卡片从该终态投影“已取消”且不再可提交；失败时释放 claim，保持原卡片可重试。`REVOKED` 只表示服务端撤销，不代表用户成功取消。

取消成功后，在 Action 与结果消息同一事务中清除本任务的 Root 工作记忆（客户绑定、正文、下一步、问题及任务级纠正），并在会话上下文记录取消结果消息 ID 作为近期消息的持久下界；Root 只读取该 ID 之后的近期消息，普通历史消息仍可展示，Action 按保留策略清理也不得解除下界。用户需在聊天输入框发送完整的新请求：从 Root 重新分类、解析和校验客户，不恢复被取消的 checkpoint，也不复用其客户和内容；新请求缺少必要信息时正常澄清。失败回滚不得写入下界或清除记忆。未取消的有效补充仍按原续接合同处理。

### 3.7 历史待办确认与延期操作边界（旧 Case）

历史待办确认是一个轻量的“完成状态确认”交互，只回答这项待办是否已经完成：

- 新建确认 Case 统一使用“现在完成了吗?”文案；
- Agent UI 和兼容确认渠道只展示“已完成”“先放着”“不管了”三个选项；
- “先放着”和无法判断的非完成回复都不得修改待办时间或状态；
- 延期是独立的 `transition_follow_up_task` 操作，不作为历史待办确认的选项或追问；
- 已存在的旧 Case、投影消息和投递快照不做破坏性数据清洗，在读取边界统一转换旧的“需要延期吗?”/“不需要继续跟进了吗?”文案；
- 旧数据原始字段仍保留，避免历史数据迁移影响 dev 环境和审计证据。

## 4. 客户解析、任务内绑定和创建

### 4.1 客户解析顺序

首次处理：

```text
语义解析
→ Customer Resolver
→ 服务端权限/存在性校验
→ customer_id 绑定到当前任务
```

以下规则仅适用于尚未取消的有效任务；取消后新请求不得沿用旧任务的客户绑定：

补充轮次：

```text
复用任务已绑定的 customer_id
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

只在服务端确认可安全重试时处理尚未成功的活动 command；不得重放已成功的客户创建，也不得重试结果未知的写入。

## 5. 现行路径

```text
销售助手 /assistant → /v1/assistant
    ├── Customer Resolver
    ├── Canonical Activity Structurer
    ├── Canonical Activity Evaluator
    ├── Next Action Gate
    ├── 持久任务、等待及冻结确认
    └── create_final_from_assistant2()

页面活动 API
    └── create_pending_from_form()
            └── CustomerActivityAIJob
                    └── structure + evaluate
                            └── finalize_pending_from_ai()

页面表单活动最终化 → CustomerActivityPostCommitJob
销售助手活动最终化 → 独立跟进任务投影；商机建议与后续写命令另行处理
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

### 6.2 `create_final_from_assistant2()`

事务内一次性：

```text
创建活动
写最终整理内容
写最终摘要/下一步行动/时间
写最终评分、原因和分项
写 processing_status=COMPLETED
写 effectiveness_status=COMPLETED
登记销售助手跟进任务投影
由调用方在同一事务写冻结命令执行回执并结算任务
提交
```

不得：

```text
创建 CustomerActivityAIJob 或旧 Agent PostCommitJob
调用 trigger_processing()
调用 trigger_evaluation()
```

符合商机建议条件时，在活动提交之后独立处理；后续失败不能回滚活动。

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
标记 AIJob COMPLETED
提交
```

禁止先提交整理结果、再提交评分结果。

## 7. 两条活动路径

### 7.1 销售助手路径

```text
用户输入
→ 语义解析
→ 客户解析/复用
→ 内容整理
→ 评分
→ score < 60：单问题补充，不写入
→ score >= 60：下一步行动门禁
→ 门禁不通过：补充，不写入
→ 门禁通过：展示冻结确认
→ 用户确认：/v1/assistant → create_final_from_assistant2()
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

旧 Agent 建议任务独立于 PostCommitJob。其失败、重试或耗尽不修改活动状态；销售助手后续建议不依赖旧任务。

## 9. 幂等与并发

### 9.1 AIJob 唯一性

数据库唯一约束至少覆盖：

```text
team_id + activity_id + activity_revision + job_type
```

不能仅使用“先查再插”的应用层判断。

### 9.2 销售助手命令幂等

活动使用团队范围内稳定的 `submission_id` 与冻结指纹；重放必须匹配原客户和冻结载荷，不重新创建活动、评分或下游任务。商机命令使用各自的 `command_id` 和目标效果，详见[销售助手命令契约](../runtime/assistant-command-contract.md)。

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

- 页面表单最终化时登记 PostCommitJob；销售助手活动不创建旧 Agent PostCommitJob，登记独立的跟进任务投影。活动事实与登记同事务，任务在提交后执行。
- 销售助手的商机建议与跟进任务投影独立于活动写入结果；失败不回滚活动。

所谓后台任务必须立即返回；如果请求需要等待任务完成，就不属于本方案中的后台任务。

## 11. 商机流程

### 11.1 建议生成

销售助手活动成功后独立生成商机建议。建议本身不创建商机。

触发条件：

```text
销售助手来源
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
→ /assistant 投影服务端签发的商机交互
→ 用户确认并按当前等待提交或取消
→ 独立商机创建命令，校验权限及审批
```

弃用旧重型弹窗。

### 11.4 商机推进

仅当用户明确要求并授权推进时，启动独立商机阶段命令。描述“已进入某阶段”不等于授权系统修改阶段。

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

## 15. 运行一致性与可观测性

至少监控：

```text
AIJob queued/running/retry_pending/exhausted 数量
最老 queued 任务年龄
AIJob 执行耗时和跳过原因
销售助手活动却存在 AIJob
页面 PENDING 活动却没有 AIJob
AIJob COMPLETED 但活动未完成
页面表单活动最终化但没有 PostCommitJob
同一 revision 多任务
活动删除后任务仍在重试
```

对账服务可幂等修复：

- 页面 PENDING 活动缺 AIJob；
- 已最终化页面表单活动缺 PostCommitJob；
- 删除活动仍有可执行任务。

如果 AIJob 已 `COMPLETED` 但活动没有最终结果，应作为事务不变量破坏告警，不能静默重新评分。

## 16. 前端合同

- 活动列表和详情继续使用现有展示方式；
- 用户不看到 lease、attempt_count、Job ID 等内部信息；
- 低质量交互一次只展示一个补充问题；
- 销售助手商机、补充和确认交互使用服务端签发的当前等待，回执及表单投影规则见 [Agent UI 平台边界](../runtime/agent-ui-platform.md)；
- 刷新恢复最新任务投影，历史卡片只读；确认、提交、取消按版本及幂等门禁防重。

## 17. 关键系统不变量

1. 销售助手最终活动不创建 CustomerActivityAIJob。
2. 页面活动永远通过 CustomerActivityAIJob 整理和评分。
3. 一条活动只保存一个最终评分。
4. AI 中间整理或评分结果不分步写入活动。
5. 页面表单的 PostCommitJob 只在活动最终化时登记。
6. 页面低分不是技术失败，活动保留且 PostCommit 继续。
7. 商机建议、创建或推进失败不影响活动。
8. 活动删除后所有相关后台任务静默 `SKIPPED`。
9. Worker 重试不重复创建活动、评分或业务副作用。
10. 恢复不得重复执行已完成命令或重试提交结果未知的写入。
11. 客户只在首次解析或明确切换时搜索；恢复仍重新校验权限和存在性。
12. 不创建线索，不把回款、合同等范围外动作带入本期。

## 22. 文档维护规则

变更活动表单、AIJob、最终化或删除不变量时，同步更新本文并记录决策依据；历史迁移计划和验收报告可从 Git 历史查阅。
