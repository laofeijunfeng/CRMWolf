# 客户详情业务旅程身份设计

- 日期：2026-09-16
- 状态：已确认方向，待书面审阅
- 范围：客户详情「项目旅程」改挂业务旅程；商机详情瘦身为商机对象页；`CustomerDealJourney.public_id` 与客户下旅程薄读接口
- 上游决定：客户详情列表一行 = 一条业务旅程；独立商机详情只做商机自己的活；合同 / 回款 / 发票 / License 只在客户 → 业务旅程里操作；赢单 / 输单 / 编辑只留独立商机详情；旅程页仍可推进采购阶段；创建入口仍是「新建商机」；独立旅程管理页不做；产品面默认 1:1，不做共享 / 解绑 UI；对外一律 `public_id`
- 相关规范：`CRM-Docs/design-agent/runtime/customer-intelligence-profile.md` §8、`CRM-Docs/design-system/patterns/kanban-page.md`、`docs/ux/p1-packages/04-object-context-hierarchy.md`、`docs/superpowers/specs/2026-09-14-business-journey-board-opportunity-date-filters-design.md`
- 相关实现：`CRM-Client/src/views/CustomerDetailSheet.vue`、`CRM-Client/src/components/panels/OpportunityDetailContent.vue`、`CRM-Client/src/components/panels/OpportunitiesPanel.vue`、`CRM-Server/app/models/deal_journey.py`、`CRM-Server/app/services/deal_journey_service.py`、`CRM-Server/app/api/business_journey_board.py`

## 1. 背景与目标

客户详情第四页签文案是「项目旅程」，数据是 `GET /v1/opportunities/?customer_id=`，点进去是 `OpportunityDetailContent`。该组件把审批、采购阶段、合同、回款、发票、License 全部挂在商机上。

领域层的交易主线已经是 `CustomerDealJourney`：

- 看板数据源是 `crm_customer_deal_journeys`，阶段由旅程状态 + 主商机赢率 + 合同 / 回款 / 发票闭环推断
- 客户档案把旅程当交易主线，商机 / 合同 / 回款只作引用
- 创建商机时 `ensure_for_opportunity` 自动建旅程，产品面默认 1:1
- `PATCH /v1/opportunities/{id}/deal-journey` 允许显式共享 / 解绑，前端没有入口

结果：用户从客户详情点「项目旅程」看到的是商机；履约对象语义上不属于商机。

目标：

1. 客户详情该页签身份改为业务旅程，列表和详情都展示旅程状态（看板阶段 + 采购类型）
2. 商机详情只保留基本信息、审批进度、商机进度、编辑 / 赢单 / 输单
3. 合同 / 回款 / 发票 / 许可申请只在客户 → 业务旅程这条履约工作台上操作
4. 写路径（建商机、审批、推进阶段、合同 / 发票 / 回款 / License）不改对象和接口
5. 旅程对外使用 `public_id`，内部 `id` 不出现在新读接口、客户详情栈、商机响应的对外字段里

## 2. 非目标

- 独立业务旅程管理页、看板卡片点进旅程详情
- 任何写接口语义、权限码、旅程事件模型
- 共享 / 解绑旅程的产品 UI
- 用档案 `GET /customers/{id}/profile/journeys` 当交易详情
- 把合同 / 回款 / 发票 / License 聚合进旅程读接口
- 给合同、回款、活动、承诺补旅程 `public_id`（那些响应里的内部 `deal_journey_id` 本期不扩范围；新旅程读接口和商机对外字段必须用 `public_id`）
- 给无旅程的孤儿商机补数据或并进旅程列表
- 把客户详情 footer / 空态「新建商机」改成「新建业务旅程」

## 3. 方案选择

采用「拆壳，不拆写路径」。

放弃：

- 只换页签文案、详情仍是商机：和「一行 = 旅程」、商机详情只做商机都对不上
- 做成完整旅程模块（管理页 + 看板跳转 + 商机工作台换身份）：超出本期
- 零后端、用商机列表按 `deal_journey_id` 去重：无主商机的旅程进不来，且继续把内部 int 当身份

## 4. 对象身份

| 对象 | 职责 | 禁止 |
|---|---|---|
| 业务旅程 `CustomerDealJourney` | 客户下的交易壳。列表身份、详情顶栏阶段、履约工作台（合同 / 回款 / 发票 / License） | 自己变成可编辑的商机主数据；本期不提供「新建旅程」 |
| 商机 `Opportunity` | 销售对象：基本信息、审批、采购阶段、赢 / 输 / 编辑 | 再挂合同链 |
| 合同 / 回款 / 发票 / License | 写入仍走各自对象和接口 | 改归属键或新建写接口 |

产品面默认 1:1：一行旅程对应 `primary_opportunity`。模型允许多商机共享一条旅程，客户 / 商机 UI 没有该入口，本期不为共享做界面。无主商机（API 解绑残留）仍出现在旅程列表；详情没有审批 / 商机进度，合同面板为空。License 仍按客户拉，走现有「无已签合同」过滤（只显示未绑定合同的申请）。

P1-PKG-04 的对象栈从 `客户 → 商机 → 合同 → 回款` 改为客户详情内：

```text
客户 → 业务旅程 → 合同 → 回款计划 → 回款记录
```

独立商机列表不进入这条栈。Agent 打开商机仍走瘦身后的商机详情。

## 5. `public_id`

`crm_customer_deal_journeys` 目前只有内部 `id`。看板返回 `journey_id: int`。商机响应的 `deal_journey_id` 也是内部 int。旅程一旦作为客户详情的对外对象，必须有 `public_id`。

### 5.1 列与生成

- 列：`public_id VARCHAR(64) NOT NULL`，全局唯一索引
- 生成：`generate_public_id("djy")` → `djy_` + 32 位 hex
- 校验：`DEAL_JOURNEY_PUBLIC_ID_PATTERN = ^djy_[0-9a-f]{32}$`，`is_deal_journey_public_id`
- 模型 `default=` 与客户 / 商机相同，新建旅程自动带 `public_id`

前缀不用 `dj`：过短，且和内部 `id` 口头混淆。`djy` 与现有 `cus` / `opp` / `lead` 风格一致。

### 5.2 迁移

Alembic，模式对齐 `066_opportunity_public_ids.py`：

1. 加可空列
2. 对 `public_id IS NULL OR public_id = ''` 的行按 `id` 回填 `djy_{uuid4().hex}`
3. 改为 `NOT NULL`
4. 唯一索引 `uq_crm_customer_deal_journeys_public_id`

无行不生成。回填必须可重复跑（列已存在则跳过 add）。downgrade 删索引和列。

新建旅程不得依赖迁移；ORM default 必须在应用层生效。测试：空库升级后新建旅程有合法 `public_id`；有历史行的升级后无空 `public_id`、无重复。

### 5.3 对外字段

新读接口的 `id` 与 `public_id` 都是 `djy_…`，与客户 / 商机响应一致，不返回内部 int。

商机对外响应：

- `deal_journey_id` 改为旅程 `public_id`（`str | None`），不再返回内部 int
- `OpportunityDealJourneyUpdate.deal_journey_id` 同步改为 `public_id` 字符串或 `null`；非法格式 404，与商机路径校验一致
- 前端 Zod / 类型跟这次改；`passthrough()` 不能再把内部 int 当身份用

看板 `journey_id` 本期仍为内部 int。看板首版明确不做点击跳转；改看板身份不在本期。若后续看板要点进客户详情旅程，再把卡片 `id` 换成 `public_id`。

客户活动响应里的 `deal_journey_id: int` 本期不动。档案投影 JSON 里的旅程 `id` 仍是内部 int，档案前端只做摘要，不作为客户详情导航键。

## 6. 读接口

写路径不动。不复用看板（全团队、且只要已审批主商机），不复用档案投影。

```text
GET /v1/customers/{customer_public_id}/deal-journeys
GET /v1/customers/{customer_public_id}/deal-journeys/{journey_public_id}
```

权限：`check_customer_view_permission`，与打开客户详情相同。不加新权限码。路径里的 `journey_public_id` 必须通过 `is_deal_journey_public_id`，否则 404「业务旅程不存在」。旅程必须属于该客户和当前团队。

列表：该客户全部非 `ARCHIVED` 旅程，含未审批主商机。看板那层「必须有 `OPPORTUNITY_APPROVED`」不搬过来，否则现有未审批商机会从客户详情消失。排序：`last_event_at DESC NULLS LAST`，再 `id DESC`。首版不分页，一次返回该客户全部非归档旅程（数量与商机同量级）。CRUD 走 `get_by_public_id` / `list_by_customer`，API 层不直接 `db.query`。

阶段：把看板 `_infer_stage` 抽成共用函数，列表 / 详情 / 看板走同一套。返回 `current_board_stage` 与中文 `current_board_stage_label`（初期交流 / 持续推进 / 即将签约 / 签约中 / 回款中 / 开票中 / 已完成 / 已输单）。未审批主商机按赢率落到销售推进列，通常是初期交流。无主商机且旅程未完成 / 未输单：落到 `early_communication`。

列表 / 详情同一 schema：

| 字段 | 来源 |
|---|---|
| `id` / `public_id` | `djy_…` |
| `name` / `status` | 旅程 |
| `current_board_stage` + `current_board_stage_label` | 共用推断 |
| `amount` | 主商机 `total_amount`，无主商机为 `0` |
| `purchase_type` | 主商机；无主商机为 `null` |
| `started_at` / `closed_at` / `last_event_at` | 旅程 |
| `primary_opportunity` | `public_id`、名称、商机状态、审批阶段、赢率、预计成交日期；无主商机为 `null` |

详情不聚合合同 / 回款 / 发票 / License。正文里的审批、阶段步进、合同、回款、发票、License 仍打现有对象接口，用 `primary_opportunity.public_id` 和现有 `getContractByOpportunity` 等。

`targetOpportunityId` 继续可用：打开客户详情后，用该商机的 `deal_journey_id`（此时已是 `public_id`）落到对应旅程。商机没有旅程时停在业务旅程列表，不假装打开商机详情。新增 `targetJourneyId`（`djy_…`）供商机详情「查看业务旅程」深链。

创建后刷新旅程列表，不新建写接口。

## 7. 页面结构

### 7.1 客户详情

页签 `opportunities` / 「项目旅程」→ `journeys` / 「业务旅程」。`targetPanel` 字面量同步改；迁移 `Customers.vue`、hover card 等全部调用方，不保留 `opportunities` 别名。

`OpportunitiesPanel` 替换为 `DealJourneysPanel`：

- 标题「业务旅程」，空态「暂无业务旅程」
- 主信息：旅程名称
- meta：看板阶段 label · 金额 · 采购类型（新购 / 续购 / 增购）；无主商机不显示类型
- 行点击打开旅程详情，不是商机

Footer / 空态按钮仍是「新建商机」，成功后刷新旅程列表。

栈：`DetailObjectType` 增加 `journey`。客户详情栈不再 push `opportunity`。从旅程打开合同：`parentType: 'journey'`，`parentId` 为旅程 `public_id`。`DetailContextHeader` 标签：业务旅程。

选中态：`selectedOpportunityId` → `selectedJourneyId`（`djy_…`）。

### 7.2 业务旅程详情 `DealJourneyDetailContent`

只挂在 `CustomerDetailSheet`。

```text
顶栏：旅程名称 · 看板阶段 · 采购类型
金额在右侧
面包屑：客户详情 → 业务旅程

基本信息          ← 主商机字段，只读展示
审批进度          ← ApprovalProcessGeneric，对象仍是 OPPORTUNITY
商机进度          ← OpportunityStageStepper，可点击推进
合同 / 回款 / 发票 / 许可申请
```

顶栏不要商机状态徽章（跟进中 / 赢单 / 输单）。阶段已经表达旅程进度。

页脚没有编辑 / 赢单 / 输单。新建合同、申请发票 / License 仍在各自面板上。

审批提交 / 通过 / 驳回 / 撤回留在旅程页（推进门禁）。驳回后「改完再提交」不再内嵌 `OpportunityFormDialog`；提示去独立商机详情编辑后再回来提交。

无主商机：基本信息 / 审批进度 / 商机进度显示空态「该旅程暂无主商机」。本期合同仍走 `getContractByOpportunity(primary_opportunity.public_id)`，无主商机则不请求合同，合同 / 回款 / 发票面板为空。不新增按旅程拉合同的接口。

### 7.3 瘦身后的商机详情

`OpportunityDetailSheet`、商机列表、Agent 打开商机，都走瘦身后的 `OpportunityDetailContent`：

```text
顶栏：商机名称 · 商机状态 · 审批状态 · 采购类型 · 金额
入口：查看业务旅程（deal_journey_id 为空则不显示）

基本信息
审批进度
商机进度（可推进）
页脚：编辑 / 赢单 / 输单
```

不再加载、不再渲染合同 / 回款 / 发票 / License。`getContractByOpportunity` 从这条路径消失。

「查看业务旅程」：打开所属客户详情，`targetPanel=journeys`，`targetJourneyId=deal_journey_id`。

### 7.4 文案

审批区标题统一「审批进度」。阶段区统一「商机进度」。步进器和审批组件不新写。不抽第三层履约面板容器，除非拆完出现大段复制。

## 8. 数据流

```text
客户详情 · 业务旅程页签
  GET /v1/customers/{cus}/deal-journeys
        ↓
DealJourneysPanel
        ↓ 行点击
DealJourneyDetailContent
  GET /v1/customers/{cus}/deal-journeys/{djy}
  GET /v1/opportunities/{opp}                 ← 主商机，供基本信息 / 审批 / 阶段
  GET /v1/contracts/opportunity/{opp}         ← 合同
  现有回款 / 发票 / License 接口              ← 与现在相同的过滤

独立商机详情
  GET /v1/opportunities/{opp}
  不再请求合同链
  「查看业务旅程」→ 客户详情 + targetJourneyId
```

写：

- 新建商机 → 现有创建接口 → `ensure_for_opportunity` 自动建旅程（带 `public_id`）→ 刷新旅程列表
- 推进阶段 / 审批 / 合同 / 发票 / License → 现有接口，主体仍是商机或合同，不是旅程

## 9. 测试与验收

后端：

- 迁移：历史行全部有唯一 `djy_` `public_id`；新建旅程自动带合法 `public_id`
- 列表：含未审批主商机对应旅程；不含 `ARCHIVED`；不属于该客户 404；无客户查看权限 403
- 非法 `journey_public_id`（内部 int、`opp_…`、空）→ 404
- 阶段：与看板 `_infer_stage` 同一输入得到同一 `current_board_stage`
- 商机响应 `deal_journey_id` 为 `djy_…` 或 `null`，不再是 int
- `PATCH .../deal-journey` 接受 `djy_…` 或 `null`；内部 int 404

前端：

- 客户第四页签文案「业务旅程」；列表渲染阶段 label，不渲染「商机」标题
- 栈类型为 `journey`，从旅程打开合同后返回旅程而不是商机
- `targetOpportunityId` 落到对应旅程；`targetJourneyId` 直接打开该旅程
- 瘦身后的商机详情没有合同 / 回款 / 发票 / License；有旅程时有「查看业务旅程」
- 旅程详情没有编辑 / 赢单 / 输单；有主商机时可推进阶段

手工：

- 客户 → 业务旅程 → 合同 → 返回旅程
- 商机列表 → 瘦详情 → 查看业务旅程 → 落在同一客户的对应旅程
- 未审批商机创建后出现在客户业务旅程列表

不新挂 Vue 大页测试。用现有 `CustomerDetailSheet.opportunity-drilldown.spec.ts` 改成旅程下钻；商机详情组件测瘦身。

## 10. 风险

1. 独立商机页不再直达履约对象。「查看业务旅程」是唯一回收路径，深链必须可用。
2. `targetOpportunityId`、客户 hover 打开商机、`Customers.vue` 的 `openCustomerOpportunity` 必须改成打开旅程。漏改会停在列表或开错对象。
3. 驳回后再提交：旅程页不再内嵌商机编辑。
4. 无 `deal_journey_id` 的孤儿商机不会出现在客户业务旅程页签。本期不补数据。
5. 看板、档案、活动响应仍可能带内部旅程 int。客户详情导航禁止使用那些字段。
6. 商机 `deal_journey_id` 从 int 改成 string 是破坏性 API 变更。前端 schema 必须同步；没有外部 SDK 依赖时不做兼容层。
7. 合同加载仍按主商机。默认 1:1 成立；共享旅程（仅 API）下旅程详情只能看到主商机那份合同。

## 11. 实现顺序

1. `public_id` 列、生成器、迁移、模型 default
2. 抽出 `_infer_stage`；客户下旅程列表 / 详情读接口；商机响应字段改为 `public_id`
3. `DealJourneysPanel` + `DealJourneyDetailContent`；客户详情页签 / 栈 / 深链
4. 瘦身 `OpportunityDetailContent`；加「查看业务旅程」
5. 改现有下钻测试；定向跑后端迁移 / 读接口测试和前端详情测试
