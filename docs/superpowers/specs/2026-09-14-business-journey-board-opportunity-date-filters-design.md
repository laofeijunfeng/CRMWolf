# 业务看板商机日期筛选设计

- 日期：2026-09-14
- 状态：已确认方向，待书面审阅
- 范围：系统业务看板 `business-journey-board` 筛选；`GET /v1/business-journey-board/` 查询参数；前端筛选接线
- 上游决定：保留现有「最近动态时间」；新增主商机创建时间和预计成交日期；多个日期条件 AND；筛选项文案用「预计成交日期」而不是「预计回款时间」
- 相关实现：`CRM-Client/src/views/BusinessJourneyBoard.vue`、`CRM-Client/src/api/businessJourneyBoard.ts`、`CRM-Server/app/api/business_journey_board.py`

## 1. 背景与目标

业务看板当前筛选只有两项：

- `last_event_at`：旅程最近业务动态，映射到 API 的 `start_date` / `end_date`
- `owner_id`：负责人

销售要按商机创建时间和预计成交日期看板上的旅程。产品口语里的「预计回款时间」在本系统没有对应商机字段：

- 商机表单、商机列表、审批详情里的字段是 `Opportunity.expected_closing_date`，文案是「预计成交日期」
- 合同回款计划的应回款日是 `PaymentPlan.due_date`，不属于商机

本设计只加主商机上的两个日期筛选，不把回款计划日期混进来。

目标：

1. 看板筛选增加「商机创建时间」和「预计成交日期」
2. 现有「最近动态时间」和「负责人」保持语义与参数不变
3. 已启用的日期条件互相 AND，再与负责人、权限范围、已审批门槛 AND
4. 不改卡片展示、列结构、自定义视图存储格式

## 2. 非目标

- 不筛选 `PaymentPlan.due_date` 或其他回款记录日期
- 不在卡片上展示创建时间或预计成交日期
- 不新增看板排序
- 不把 `start_date` / `end_date` 重命名为 `last_event_at_*`
- 不把新日期区间写进响应的 `period_start` / `period_end`
- 不做一次只能选一个日期维度的互斥控件
- 不改自定义视图 schema；旧视图没有这两个 key 时行为与现在相同

## 3. 方案选择

采用「保留现有最近动态参数，再加两对显式商机日期参数」。

放弃：

- 三个日期都改成成对参数并废弃 `start_date` / `end_date`：对称，但会破坏现有客户端映射和已保存视图，收益不够
- 一个 `date_field` 枚举加共用区间：一次只能筛一个日期，与「全部 AND」冲突

筛选对象仍是旅程卡，不是商机列表。日期作用在 `CustomerDealJourney.primary_opportunity_id` 对应的主商机上。看板已经只返回已审批且存在 `OPPORTUNITY_APPROVED` 事件的旅程；这两类旅程都有主商机，且 `created_time`、`expected_closing_date` 非空，不必为日期筛选单独处理空值卡。

## 4. 数据流

```text
ListFilterPopover
  ├── last_event_at            → getDateBounds → start_date / end_date
  ├── created_time             → getDateBounds → created_time_start / created_time_end
  ├── expected_closing_date    → getDateBounds → expected_closing_date_start / expected_closing_date_end
  └── owner_id                 → getDelimitedFilterValues → owner_id
        ↓
GET /v1/business-journey-board/
        ↓
已审批主商机
AND OPPORTUNITY_APPROVED 事件
AND owner scope
AND last_event_at 区间（若有）
AND Opportunity.created_time 区间（若有）
AND Opportunity.expected_closing_date 区间（若有）
        ↓
按现有规则分列并汇总
```

## 5. 接口契约

`GET /v1/business-journey-board/` 增加四个可选日期参数。现有 `start_date` / `end_date` / `owner_id` / `limit` 不变。

| 参数 | 作用字段 | 比较 |
|---|---|---|
| `start_date` / `end_date` | 旅程 `CustomerDealJourney.last_event_at` | datetime，右开；复用 `_date_range` |
| `created_time_start` / `created_time_end` | 主商机 `Opportunity.created_time` | datetime，右开；复用 `_date_range` |
| `expected_closing_date_start` / `expected_closing_date_end` | 主商机 `Opportunity.expected_closing_date` | `Date` 闭区间 `>= start AND <= end` |

规则：

- 每对内部若同时传入且 start > end，返回 400，文案沿用「开始日期不能晚于结束日期」
- 不同日期对互相独立；同时存在则 AND
- 只传 start 或只传 end 合法
- 未传的对不生效
- 响应仍只回 `period_start` / `period_end`，表示最近动态筛选区间，不回传商机日期区间

前端 `BusinessJourneyBoardParams` 增加同名四字段并透传。

## 6. 前端接线

`BusinessJourneyBoard.vue` 的 `filterFields` 在现有两项后增加：

- `created_time`，标签「商机创建时间」，`type: 'date'`
- `expected_closing_date`，标签「预计成交日期」，`type: 'date'`

`loadBoard` 继续用 `getDateBounds` 解析 `eq` / `after` / `before`。不改 `ListFilterPopover`、自定义视图、卡片 UI。

## 7. 测试

后端在现有看板测试旁新增 API 用例，不塞进 `test_backend_business_scenarios.py`：

- 只筛创建时间：区间内命中、区间外排除
- 只筛预计成交日期：区间内命中、区间外排除
- 两个商机日期同时启用：AND
- 商机日期与 `last_event_at` 同时启用：AND
- 任一对 start > end：400

前端看板没有现成视图测试。用轻量单测钉住 params 映射；不为这次改动挂 Vue 页面测试。卡片展示和列结构不测。

## 8. 风险

- `start_date` / `end_date` 名字仍偏泛。靠筛选字段 key、API description 和本 spec 标明它们只表示最近动态，不靠这次重命名修复。
- 口语「预计回款」容易和 `PaymentPlan.due_date` 混淆。筛选项必须写「预计成交日期」。
