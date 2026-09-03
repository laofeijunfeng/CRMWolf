# Agent API 开发环境场景化测试报告

- **测试日期：**2026-09-02
- **测试类型：**API 层场景化验收测试
- **测试范围：**客户活动 Agent Workflow parity 补齐能力 + Agent 既有 API 能力
- **测试代码：**`CRM-Server/tests/integration/test_agent_api_dev_scenarios.py`
- **关联规格：**[客户活动 Agent Workflow Parity 实施规格](./customer-activity-workflow-parity-spec.md)
- **关联差异证据：**[旧 Agent 流程到新 Workflow 的 Parity Matrix](./legacy-workflow-parity-matrix.md)
- **关联实施状态：**[客户活动 Workflow 实施状态](./customer-activity-workflow-implementation-status.md)

## 1. 测试目标

本轮目标不是只验证某一个接口返回 200，而是围绕真实 CRM 业务对象构造 100+ 条可重复执行的 Agent API 场景，验证：

1. Agent 原有会话、会话查询和 SSE 对话能力没有因 Workflow 迁移失效；
2. 本次补齐的客户活动质量门禁、最终评分一次写入和后台任务分流行为符合约定；
3. 页面表单提交跟进记录/会议纪要时，能够立即保存原始活动并进入后台 AIJob pipeline；
4. Agent 已完成最终整理和评分后，能够直接写入最终活动，不再重复评分，并登记后续后台任务；
5. 低质量或无效评分在 API 层 fail-closed，不能写入 Agent 活动；
6. 测试数据来自开发环境数据库中的真实客户、活动和商机分布，而不是完全脱离业务的空白 mock 数据。

本报告中的测试是**API 层确定性验收**，不等价于真实 LLM 质量验收，也不等价于真实 Worker、浏览器和部署环境的全链路验收。

## 2. 测试环境

### 2.1 数据库

- **环境：**dev
- **数据库：**MySQL
- **连接：**`localhost:3307`
- **数据库名：**`crm_db`
- **团队范围：**team `1`
- **测试用户：**开发环境销售，用户 ID `1`

### 2.2 测试数据快照

测试启动时从开发数据库读取对象数量，并从 team `1` 读取真实客户作为场景数据来源。当前快照如下：

| 数据对象 | 数量 |
| --- | ---: |
| 用户 | 10 |
| 客户 | 84 |
| 客户活动 | 142 |
| 商机 | 35 |
| Agent 会话 | 933 |
| 客户活动 AIJob | 21 |

场景使用的真实客户示例包括：

- 河南双汇发展股份有限公司
- 广东智通人才连锁股份有限公司
- 光大证券股份有限公司
- 上海叠纸互娱网络科技有限公司
- 中国科学院信息工程研究所
- 上海云岚架构验证科技有限公司

测试还读取真实客户已有的活动数和商机数，用于选择客户和形成场景上下文；不会把客户名称、活动数量或商机数量硬编码为脱离数据库的假数据。

### 2.3 身份与数据保留方式

- 持久化验收使用真实密码登录接口 `POST /api/v1/auth/login-password`；
- 登录账号为 `eddie@apifox.com`，对应 dev 数据库用户 ID `1`，当前团队为 team `1`；密码只通过环境变量传入，没有写入代码或报告；
- 测试使用真实 FastAPI 路由、真实 schema、真实 ORM、真实认证、真实团队解析、真实客户权限解析和真实 durable-work 登记逻辑；
- 本次按用户要求使用持久化模式，测试产生的 Agent 会话、客户活动和 durable work 不回滚，保留在 dev 数据库中供页面查看；
- 每次持久化运行会生成独立的运行标签，避免重复执行时撞上 `submission_id` 唯一约束；
- 测试代码仍保留默认事务回滚模式，便于后续无污染回归；本报告记录的是持久化模式的最终执行结果。

### 2.4 测试替身边界

- 不调用真实 LLM；仅替换 Root Orchestrator 的编排结果为确定性 Workflow 结果；
- 保留真实 `AgentApplicationService`、真实 `AgentTurnRepository.begin/complete`、真实用户/Agent 消息持久化和真实历史查询 API，因此 Agent 对话内容会真实落库并可由页面读取；
- `customer_activity_write_service.kick` 在场景测试中不启动实际后台 Worker，因此任务记录会保留为可观察的 durable work，避免测试过程中被异步消费掉；这不等价于 Worker 执行验收。

## 3. 用例总览

本轮共收集并执行 **150 条测试用例**，分布如下：

| 测试组 | 用例数 | 主要验证内容 |
| --- | ---: | --- |
| Agent 会话创建 | 30 | 会话创建、团队/用户归属、初始状态、session key |
| Agent 会话列表/分页/状态筛选 | 20 | 默认列表、分页边界、不同 page size、状态过滤、权限边界 |
| Agent SSE 对话 API 合同 | 20 | SSE content type、事件顺序、final UI、done、鉴权和 request id 透传、用户/Agent 消息持久化和历史读取 |
| 页面表单客户活动 durable pipeline | 30 | 表单来源、PENDING 状态、AIJob、异步返回、任务分流 |
| Agent 已完成评分活动写入 | 30 | 最终评分一次写入、Agent 来源、PostCommitJob、商机建议任务 |
| Agent 低分/无效评分拒绝 | 10 | 低于 60 分或无效评分 fail-closed，禁止写入 |
| 既有客户活动查询 | 10 | 真实客户活动列表、分页参数、客户边界和兼容字段 |
| **合计** | **150** | **全部通过** |

## 4. 详细测试矩阵

### 4.1 Agent 会话创建（30 条）

覆盖 30 个独立会话创建场景，验证：

- `POST /api/v1/agent/sessions` 返回 HTTP `201`；
- 返回会话属于 team `1` 和 user `1`；
- 创建标题正确保存；
- 初始状态为 `ACTIVE`；
- 返回的 `session_key` 使用 Agent 会话格式。

这些用例覆盖了 Agent 迁移后的基础会话容器能力，确保后续 Workflow checkpoint 和多轮对话有稳定入口。

### 4.2 Agent 会话列表、分页和状态筛选（20 条）

覆盖默认查询、不同 page/page_size 组合、第二页及后续页、较大 page size，以及 `ACTIVE`、`CLOSED`、`ARCHIVED`、`PENDING` 等状态筛选场景，验证：

- `GET /api/v1/agent/sessions` 返回 HTTP `200`；
- 返回结构包含 `items`、`total`、`page`、`page_size`、`total_pages`；
- 当前页返回数量不超过 page size；
- 返回会话均属于当前团队和用户授权范围；
- 分页参数能够被 API 正确回显和执行。

### 4.3 Agent SSE 对话 API 合同（20 条）

每条用例都会先创建会话，再调用：

```text
POST /api/v1/agent/chat/stream
```

验证内容：

- 返回 HTTP `200`；
- `Content-Type` 为 `text/event-stream`；
- 事件顺序严格为：

```text
session → agent_ui(final) → done
```

- `agent_ui` 事件使用 `crm.agent.ui.v1`；
- final 消息包含最终 Agent UI 内容；
- done 事件携带正确的 session ID；
- `Authorization` header 被传递到 Agent runtime；
- `client_request_id` 被解析并透传为 UUID。

这里使用确定性 typed SSE application 只替换模型输出边界，不替换 HTTP 路由、schema、事件编码和鉴权透传逻辑。

### 4.4 页面表单客户活动 durable pipeline（30 条）

测试从开发数据库读取真实客户，并使用以下活动类型和真实业务语义模板生成场景：

- `PHONE_FOLLOW_UP`
- `WECHAT_FOLLOW_UP`
- `EMAIL_FOLLOW_UP`
- `MEETING`
- `OTHER_FOLLOW_UP`

场景示例包括电话确认试用反馈、会议需求澄清、微信补充报价、邮件确认预算、POC 复盘和供应商比较等。

验证页面表单接口：

```text
POST /api/v1/customer-activities/{customer_id}
```

结果必须满足：

- 接口返回创建成功；
- `submission_source = FORM`；
- `processing_status = PENDING`；
- `effectiveness_status = PENDING`；
- 原始 `source_content` 已保存；
- `effectiveness_score` 尚未产生；
- 返回 `durable_work.ai_job_public_id`；
- 不提前创建 `PostCommitJob`；
- 不创建 Agent-only 商机建议任务；
- 接口不等待 LLM 处理，后续由后台任务完成整理、评分和后处理。

该组同时覆盖跟进记录和会议纪要共用页面表单后台 pipeline 的 API 分流合同。

### 4.5 Agent 已完成评分活动写入（30 条）

测试调用 Agent finalized 写入接口，并提交已经由 Agent 完成的最终结构化结果和最终评分：

```text
POST /api/v1/customer-activities/{customer_id}/agent-finalized
```

场景包含不同客户、不同活动类型、不同分数、明确或为空的下一步行动以及不同的跟进时间组合。

验证结果：

- `submission_source = AGENT`；
- `processing_status = COMPLETED`；
- `effectiveness_status = COMPLETED`；
- 最终评分直接写入；
- 最终整理内容和评分在同一条活动中保存；
- 不再创建 AIJob，避免 Agent 已评分后再次评分；
- 创建 PostCommitJob；
- 创建 Agent-only `OpportunitySuggestionJob`；
- 活动来源、评分状态和 durable-work 投影与合同一致；
- `effectiveness_detail_json` 能够从 API 的 JSON 对象正确序列化并落库。

### 4.6 Agent 低分/无效评分拒绝（10 条）

覆盖以下边界：

- 0、1、10、40、55、58、59 分；
- 60 分但 `effectiveness_is_valid = false`；
- 0 分但 `effectiveness_is_valid = true`；
- 59 分但 `effectiveness_is_valid = true`；
- 低分但携带补充说明。

统一验证：

- API 返回 HTTP `422`；
- 活动不会被写入数据库；
- 评分门禁是 fail-closed，而不是依赖调用方自觉传递合格结果。

### 4.7 既有客户活动查询（10 条）

使用开发数据库中的 10 个真实客户，调用：

```text
GET /api/v1/customer-activities/{customer_id}?skip=0&limit=100
```

验证：

- 返回 HTTP `200`；
- 返回值为列表；
- 结果属于请求的客户；
- 活动列表保留 `activity_kind`、`source_content` 等现有展示所需字段；
- 既有活动可被当前 API 继续读取，未因新 Workflow 数据契约切换而丢失读取能力。

## 5. 执行命令与结果

### 5.1 用例收集

```bash
cd CRM-Server
PYTHONPATH=. RUN_AGENT_API_DEV_SCENARIOS=1 uv run pytest \
  tests/integration/test_agent_api_dev_scenarios.py --collect-only -q --no-cov
```

结果：

```text
150 tests collected
```

### 5.2 测试执行

```bash
cd CRM-Server
PYTHONPATH=. RUN_AGENT_API_DEV_SCENARIOS=1 uv run pytest \
  tests/integration/test_agent_api_dev_scenarios.py -q --no-cov
```

结果：

```text
150 passed, 180 warnings
```

警告不影响通过结论，主要包括仓库现有的 Pydantic v2 弃用/命名空间警告，以及测试事务清理阶段的 SQLAlchemy `transaction already deassociated from connection` 警告；本轮没有测试失败。

### 5.3 持久化 dev 账号验收

本次按要求使用真实账号并保留测试数据执行：

```bash
AGENT_API_DEV_TEST_EMAIL='eddie@apifox.com' \
AGENT_API_DEV_TEST_PASSWORD='通过环境变量传入' \
AGENT_API_DEV_RUN_LABEL='20260902-eddie-visible-real' \
RUN_AGENT_API_DEV_SCENARIOS=1 \
RUN_AGENT_API_DEV_SCENARIOS_PERSIST=1 \
PYTHONPATH=. uv run pytest \
  tests/integration/test_agent_api_dev_scenarios.py -q --no-cov
```

最终结果：

```text
150 passed, 370 warnings in 49.06s
```

最终持久化运行标签为：

```text
20260902-eddie-visible-real-865f657b
```

数据库复核结果：

| 持久化对象 | 本次新增/保留数量 |
| --- | ---: |
| Agent 会话 | 50 |
| Agent 对话消息（USER + ASSISTANT） | 40 |
| 页面表单客户活动 | 30 |
| Agent finalized 客户活动 | 30 |
| 客户活动 AIJob | 30 |
| 客户活动 PostCommitJob | 30 |
| 商机建议任务 | 30 |

可在页面中搜索以下标识查看本次数据：

```text
Agent API dev验收-20260902-eddie-visible-real-865f657b
【Agent API dev验收 20260902-eddie-visible-real-865f657b】
DEV-20260902-eddie-visible-real-865f657b-ACT-
```

本次修正后的 Agent 对话批次已复核：50 个会话中包含 20 个聊天会话，每个聊天会话均有 1 条 USER 消息和 1 条 ASSISTANT 消息，共 40 条消息；这些消息可通过页面历史接口读取。此前第一批 `20260902-eddie-visible-9e5746f4` 的空会话数据仍按要求保留，但不作为本次对话可见性验收批次。

此前为排查持久化测试本身的认证路径和唯一键问题，曾产生两批同样带有验收标识的页面表单数据；这些数据也按“不要删除测试数据”的要求保留，没有执行清理操作。

### 5.4 Ruff 检查

```bash
cd CRM-Server
PYTHONPATH=. uv run ruff check \
  tests/integration/test_agent_api_dev_scenarios.py \
  app/crud/customer_activity.py
```

结果：

```text
All checks passed!
```

## 6. 测试过程中发现并修复的问题

首次执行 Agent finalized 活动写入场景时发现 API 层异常：

```text
TypeError: dict can not be used as parameter
```

### 原因

`effectiveness_detail_json` 从 API schema 进入 CRUD 后仍是 Python `dict`，但数据库字段是 `TEXT`，MySQL 驱动无法直接绑定 dict 参数。

### 修复

在 `CRM-Server/app/crud/customer_activity.py` 的创建路径中，将 `effectiveness_detail_json` 的 `dict/list` 统一转换为 JSON 字符串后再写入数据库。

### 验证

修复后重新执行全部场景：

```text
150 passed
```

这说明本轮场景测试不只是“证明现有代码没问题”，还实际捕获并定位了一个会阻断 Agent 最终评分活动写入的 API/持久化问题。

## 7. 本轮已确认可用的能力

### Agent 原有能力

- Agent 会话创建；
- Agent 会话列表、分页和状态过滤；
- Agent SSE 对话入口；
- SSE 事件顺序和最终 UI 消息合同；
- 鉴权信息和客户端请求 ID 透传；
- 真实客户活动读取。

### 本次补齐能力

- 页面表单活动异步进入 durable AIJob；
- 页面表单立即返回，不同步等待模型；
- 页面表单不提前创建 PostCommitJob；
- Agent 最终结果直接写入，不重复评分；
- Agent 活动创建 PostCommitJob；
- Agent 活动独立创建商机建议任务；
- Agent 活动来源和页面表单来源分流；
- Agent 活动低于 60 分或评分无效时禁止写入；
- 评分详情 JSON 能够正确落库；
- 既有客户活动仍可查询。

## 8. 尚未由本轮测试覆盖的范围

下面这些能力不能因为本轮 150 条 API 测试通过，就宣称已经完成真实业务验收：

1. 真实 LLM 的语义解析质量；
2. 真实 Agent 低分后追问单个补充问题；
3. 用户补充后重新解析、重新评分和再次通过门禁；
4. 客户名称不完整、客户歧义、搜不到客户后的交互；
5. 客户 checkpoint 和记忆复用；
6. 真实商机建议判断；
7. 已有商机高置信度匹配后的静默忽略；
8. 商机创建/推进建议的 Agent UI “是/否”点击交互；
9. 商机内嵌表单补充、提交和取消；
10. Worker 执行 AIJob 和商机建议任务；
11. Worker 的 claim、lease、retry、recovery、exhausted 行为；
12. 删除活动与后台任务之间的竞态和任务证据保留；
13. Agent command 的幂等 replay 和并发重复点击；
14. 页面表单 `submission_id` 的重复提交幂等；
15. 商机状态变化后的 stale 静默忽略全链路行为；
16. 浏览器真实页面展示和 Agent UI 交互；
17. 真实部署环境、迁移 dry-run、备份恢复和中断重跑。

这些内容属于真实模型、后台 Worker、前端和部署联调验收，应该作为下一批测试，而不是用确定性 API 测试替代。

## 9. 已知待处理 P1 问题

基于当前代码复核，以下问题仍未被本轮 150 条测试覆盖，也不应标记为已通过：

### 9.1 Agent 幂等重放

文件：`CRM-Server/app/services/agent/tools/service.py`

现状：已有 `PENDING/AMBIGUOUS` 活动时可能直接返回 409，而不是根据相同 command 返回原 activity/result。需要补充相同 command 重放和并发调用测试，并按最终合同修复。

### 9.2 页面表单 `submission_id` 幂等

文件：

- `CRM-Server/app/schemas/customer_activity.py`
- `CRM-Server/app/services/customer_activity_write_service.py`

现状：`submission_id` 仍可为空；相同 `(team_id, submission_id)` 重试没有明确返回原活动和原 AIJob 的闭环合同。需要补充重复提交测试，避免重试触发唯一约束异常或产生重复任务。

### 9.3 商机 stale 状态静默忽略

文件：`CRM-Server/app/services/agent/workflow/planning.py`

现状：商机状态发生变化时仍可能生成“商机状态已变化，本次不再重复推进”的终止文本；当前冻结规则要求静默忽略、不提示用户。需要补充 MOVE stale API/Workflow 全链路测试并修复。

## 10. 结论

本轮已形成并执行 **150 条基于开发环境真实业务数据的 Agent API 场景测试**，执行结果为 **150 passed**。从 API 合同和确定性业务写入边界看：

- Agent 原有的会话、SSE、消息持久化、历史读取和活动查询能力可用；
- 页面表单活动已正确进入异步 AIJob pipeline；
- Agent 已完成评分的活动能够直接写入最终结果，不重复评分；
- 低分/无效评分能够被 API 层阻止；
- 活动与商机建议任务的来源和分流符合当前设计；
- 本轮测试捕获并修复了一个 JSON 明细字段写入 MySQL 的真实问题。

但本轮结论的边界是：**真实 Agent 消息持久化和历史读取已通过确定性 API 验收，但不代表真实 LLM 质量、Worker 执行、商机 Agent UI、幂等 replay、stale 竞态和部署环境全链路已经验收通过。**

下一步建议按以下顺序推进：

1. 补齐并修复 Agent command replay、页面表单 `submission_id` 幂等和商机 stale 静默忽略；
2. 在测试环境接入真实 Worker，执行 AIJob、PostCommitJob 和商机建议任务的 claim/lease/retry/recovery 验收；
3. 增加真实 LLM Golden Cases，验证客户识别、质量追问、补充重解析、已有商机匹配和商机推进建议；
4. 完成 Agent UI/browser 联调；
5. 完成迁移 dry-run、备份恢复、中断重跑和最终发布门禁。

### 5.5 页面可视化连续对话补跑

为便于在 Agent 页面直接查看完整沟通效果，新增并执行了单 Session 连续多轮验收测试。该测试不删除此前任何数据，使用同一个 Agent Session 连续发送 20 轮消息，并通过真实历史接口复核消息顺序和数量。

执行结果：

```text
1 passed, 53 warnings in 5.79s
```

本次新增可视化 Session：

```text
标题：Agent API dev验收-20260902-eddie-visible-multiturn-f6ab67c3-可视化连续对话
session_key：agent_63e1a1d95e2444d58b3513b83a991429
```

数据库复核结果：

```text
1 个 Session
40 条消息
20 条 USER + 20 条 ASSISTANT
```

该 Session 使用真实 `AgentApplicationService`、真实消息持久化和真实历史查询接口；测试仅替换 Root Orchestrator 为确定性实现，不调用真实 LLM。打开上述标题对应的 Agent 会话后，应能看到同一会话内连续的 20 轮沟通，而不是分散在 20 个独立 Session 中。

### 5.6 真实业务语义连续对话补跑（页面观察批次）

此前的“可视化连续对话”批次虽然复用了同一个 Session，但 Root Orchestrator 使用了确定性替身，不能代表真实业务语义处理。本次重新使用真实 Root Orchestrator 和当前 dev AI 配置，针对 dev 中已有客户构造 20 轮真实客户跟进分析场景，并在同一个 Session 中连续提交。

本次数据未删除，新的 Session 为：

```text
标题：Agent真实业务场景-连续20轮-20260902
session_id：1842
session_key：agent_528421ea2b9c4fd899bce4505e5a1a3b
```

场景覆盖：预算确认、采购流程、技术评审、POC 验收、竞品比较、项目暂缓、招投标信号、试点范围、合同/法务节点、下一步行动完整性等。每轮均带有 dev 中真实客户全称，并要求 Agent 评估跟进质量、提炼结果和给出下一步建议。

复核结果：

```text
20 轮请求均返回 HTTP 200
同一 Session 共 40 条消息
20 条 USER + 20 条 ASSISTANT
```

这批测试没有提交“创建跟进记录”或“创建商机”的确认操作，因此不会额外产生业务写入；目的仅是让页面展示真实 Agent 对业务语义的分析结果。部分轮次因上下文任务关系判断返回澄清提示，这是真实 Root Orchestrator 的实际行为，不是测试替身生成的固定文本。

### 5.7 真实业务批次复核更正

页面复核后发现：上述真实业务语义批次不能按“20 轮 HTTP 200”认定为业务成功。SSE 传输层均返回 HTTP 200，但 Agent 最终业务结果中包含失败/澄清状态。

`session_id=1842` 的 20 轮最终结果统计如下：

| 最终结果 | 数量 | 说明 |
| --- | ---: | --- |
| 成功返回业务分析 | 1 | 第 1 轮返回跟进完整性分析与下一步建议 |
| 交互式补充 | 1 | 第 2 轮要求补充下一步行动信息 |
| 任务切换澄清 | 3 | 第 5、7、19 轮要求明确继续原任务还是开始新任务 |
| Root/Query 模型不可用 | 3 | 第 8、10、18 轮返回识别/查询服务暂时不可用 |
| CRM Workflow 内部错误 | 12 | 第 3、4、6、9、11–17、20 轮返回“服务器内部错误” |

因此，这批数据仅能证明消息确实写入同一 Session，不能作为“真实业务能力全部通过”的测试报告。此前报告中“20 轮请求均返回 HTTP 200”的表述仅描述传输层状态，容易造成误解，现已补充业务层结果说明。

### 5.8 客户智能恢复回归补跑（2026-09-03）

在 dev 环境继续验证后台任务恢复时，发现并修复了一个会影响重试调度的历史运行状态问题。

#### 发现的问题

客户 `id=3` 同时存在较早的 `FAILED` 运行和较新的 `SUCCESS` 运行。恢复逻辑此前在选取“最新运行”时排除了 `SUCCESS`，可能错误地选中旧的失败运行，并尝试用它覆盖较新运行对应的客户档案状态，触发：

```text
CustomerProfileProjectionError: 客户档案失败状态不能覆盖其他运行
```

该异常发生在恢复扫描阶段，会使一次重试批次提前中断，表现为手工调用 `run-due` 超时或调度日志反复报错。

#### 修复内容

文件：

```text
CRM-Server/app/services/customer_intelligence_refresh_service.py
```

恢复扫描的候选状态现在包含：

```text
PENDING / RUNNING / RETRY_PENDING / SUCCESS / FAILED / CANCELLED
```

每个客户先按运行记录选出真正最新的一条，再同步客户档案投影。这样旧的失败运行不会覆盖更新的成功运行；最新运行仍为待处理或失败时，才按对应状态推进投影。

新增回归测试：

```text
CRM-Server/tests/unit/test_customer_intelligence_refresh_service.py
```

测试验证“旧 FAILED 运行位于新 SUCCESS 运行之前时，恢复扫描不报错，且客户档案保持 READY”。

#### 自动化验证

```text
57 passed
```

覆盖：刷新服务、运行服务、刷新重试调度器、对账服务和对账调度器。

#### dev 真实运行验证

使用 dev 账号 `eddie@apifox.com` 对此前对应的后台任务进行复核，未删除或重置任何测试数据：

- operation `179`（`customer_intelligence_refresh`）最终为 `SUCCEEDED`；
- 对应 run `6967` 从 `PENDING` → `RUNNING` → `SUCCESS`；
- 同批次 run `6968`、`6969` 也完成为 `SUCCESS`；
- 随后再次调用 `run-due?limit=1`，接口正常返回 HTTP `200`，该次执行结果为成功；
- 当前 dev 接口 `GET /api/v1/follow-up-tasks/confirmation-cases/pending-count` 返回 HTTP `200`，结果为 `count=228`。

首次手工调用 `run-due?limit=20` 在客户端等待 180 秒后超时，但这不是任务失败：服务端仍在异步请求链路中执行真实客户智能 Graph，之后数据库复核显示 operation `179` 及三个关联 run 均成功。该现象说明该手工接口会等待所选批次的真实 LLM 处理，不适合作为“立即返回”的后台任务入口；后台 scheduler 的正确验收标准应以 durable run / operation 的最终状态为准，而不是只看 HTTP 客户端是否在固定时间内收到响应。

### 5.9 真实 Agent 跟进记录流程回归补跑（2026-09-03）

在客户智能恢复问题处理完成后，又使用真实 Root Orchestrator 和 dev LLM 对跟进记录相关路径做了小批量页面可见回归。所有新建 Session、消息和业务数据均保留，未删除此前失败批次。

#### A. 客户跟进查询

- Session：`1849`
- 标题：`Agent真实业务回归-20260903-客户跟进-448ac04d`
- 输入：查询“河南双汇发展股份有限公司”最近的跟进记录，并评估是否有明确下一步行动；
- 结果：SSE 正常结束，最终路由为 `QUERY`；返回最近跟进内容、下一步负责人/时间/动作，并判断“有明确的下一步行动”；
- 结论：客户跟进查询和下一步行动分析可用。

#### B. 没有匹配客户

同一 Session 输入不存在的客户“火星银河科技有限公司”，最终返回：

```text
未找到与“火星银河科技有限公司”匹配的客户，请补充完整名称或客户简称。
```

该结果符合已确认约束：没有匹配客户时只提示没有匹配客户，不自动创建客户或线索。

#### C. 自然语言跟进记录 → 低质量追问 → 补充后继续

此前使用以下自然表达测试时，旧代码没有识别为跟进记录写入意图，而错误进入 `QUERY` 路径并返回 `MODEL_OUTPUT_INVALID`：

```text
我刚刚和河南双汇发展股份有限公司沟通，客户认可方案，但还没有确认预算。
请整理这条跟进并评估质量，如果缺少关键信息请先指出，不要直接写入。
```

根因是确定性跟进记录意图识别只接受“沟通了/联系过”等过去时标记，没有覆盖“刚刚和客户沟通”这种常见自然表达。

修复文件：

```text
CRM-Server/app/services/agent/orchestrator/risk.py
CRM-Server/tests/unit/test_agent_root_risk.py
```

修复后，同类输入在 Session `1850` 中得到正确结果：

1. Root 路由为 `WORKFLOW`；
2. 输出“等待补充必要信息”的过程块；
3. 输出 Agent 页面内嵌 `text_input` 表单，而不是旧弹窗；
4. 表单问题为：`下一步计划如何推进预算确认，包括具体动作和时间？`；
5. 提交“下周三上午10点确认预算，并发送正式报价”后，继续同一 Workflow；
6. 最终显示“已记录河南双汇发展股份有限公司的本次跟进。”；
7. 真实业务数据中生成活动 `id=884`，来源为 `AGENT`，最终评分 `75`，状态为 `COMPLETED`；
8. 对应活动后提交任务 `id=544` 已为 `COMPLETED`；
9. 对应该客户的客户智能后台 operation `182` 已为 `SUCCEEDED`。

这条回归证明了“Agent 先评估跟进完整性 → 发现下一步行动缺失 → 在 Agent 页面内嵌表单补充 → 补充后重新继续 → 写入最终活动 → 进入后续后台任务”的实际闭环。中间未完成的低分/补充状态没有作为最终评分历史落库，只有最终评分 `75` 被保存。

#### 自动化验证补充

意图识别修复后的单元测试：

```text
12 passed
```

此前客户智能恢复相关测试仍为：

```text
57 passed
```

需要注意：Session `1849` 中保留的早期 `MODEL_OUTPUT_INVALID` 是修复前真实回归产生的历史消息，不能用它代表修复后的当前行为；修复后的 Session `1850` 才是当前实现的验收依据。
