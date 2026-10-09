# 业务旅程当前进度与颜色统一设计

- 日期：2026-10-09
- 状态：已确认设计，待文档评审
- 范围：业务旅程列表新增当前进度列；客户管理状态 hover 的业务旅程进度条统一颜色
- 非范围：不修改后端 API 或数据库；不修改业务旅程看板卡片；不修改进度计算口径；不改变其他审批、回款、上传进度条的默认颜色

## 1. 问题

客户管理的“状态” hover 已经按业务旅程当前阶段显示进度条，但当前进度条使用固定的主色，业务旅程列表也没有直接展示当前进度。用户需要在列表中快速比较旅程推进程度，并让客户管理 hover 与业务旅程列表使用一致的进度视觉语言。

现有前端已经在 `CRM-Client/src/utils/dealJourney.ts` 中维护阶段到百分比的映射，客户管理 hover 通过 `dealJourneyProgressPercent()` 使用这套映射。因此本次不新增后端字段，也不重新定义业务进度。

## 2. 决策

采用“统一业务工具 + 通用 Progress 可选填充色”的方案：

1. 在 `dealJourney.ts` 中集中维护百分比到颜色 class 的映射函数。
2. 扩展通用 `Progress`，允许调用方传入可选的指示条 class；未传入时继续使用 `bg-primary`。
3. 业务旅程列表与客户管理 hover 都调用同一套百分比和颜色工具。
4. 只改业务旅程列表与客户管理 hover，不让所有 Progress 实例自动随百分比变色。

这样可以避免在两个页面重复颜色规则，也避免上传、审批、回款等非业务旅程进度条被动改变视觉。

## 3. 业务进度口径

继续使用现有 `DealJourneyBoardStage` 映射：

| 当前阶段 | 百分比 |
| --- | ---: |
| `early_communication` / 早期沟通 | 14% |
| `active_progress` / 积极推进 | 29% |
| `closing_soon` / 即将成交 | 43% |
| `contract_processing` / 合同处理中 | 57% |
| `payment_processing` / 回款处理中 | 71% |
| `invoice_processing` / 开票处理中 | 86% |
| `completed` / 已完成 | 100% |
| `lost` / 已流失 | 0% |

“当前进度”是当前阶段的派生展示值，不作为新的 API 查询字段，因此不提供筛选或排序能力。

## 4. 颜色规则

按进度所在的 10% 区间使用 shadcn-vue / Tailwind 色阶，进度条填充使用对应色阶的 `500`：

| 进度 | 颜色 |
| ---: | --- |
| 0–10% | `orange` |
| 11–20% | `amber` |
| 21–30% | `yellow` |
| 31–40% | `lime` |
| 41–50% | `green` |
| 51–60% | `emerald` |
| 61–70% | `teal` |
| 71–80% | `cyan` |
| 81–90% | `sky` |
| 91–100% | `blue` |

边界按整数百分比处理，`0%` 使用 orange，`100%` 使用 blue。当前阶段的实际结果为：

- 14%：amber
- 29%：yellow
- 43%：green
- 57%：emerald
- 71%：cyan
- 86%：sky
- 100%：blue
- 0%：orange

颜色只作为视觉强化；阶段文案和百分比文本必须同时保留，不能依赖颜色作为唯一状态信息。

## 5. UI 设计

### 5.1 业务旅程列表

修改 `BusinessJourneyTableView` 和 `businessJourneyListFields`：

- 在“当前阶段”后增加“当前进度”列。
- 默认显示，仍然纳入现有视图配置，可由用户隐藏或恢复。
- 列宽使用紧凑值，目标约 96px；不使用完整 hover 卡片中的长条宽度。
- 单元格显示短进度条与百分比文本，例如进度条旁显示 `57%`。
- 进度条使用派生阶段百分比及统一颜色 class。
- 单元格的 `aria-label` 包含旅程名称和百分比，例如“平台续约旅程当前进度 57%”。
- 该字段不启用筛选、排序；若字段注册表要求显式关闭能力，必须提供对应原因。

列表其他字段、行点击、详情 Sheet、看板视图和移动端表格容器行为保持不变。

### 5.2 客户管理状态 hover

修改 `CustomerDealJourneyHoverCard`：

- 保留现有业务旅程进度条位置和卡片结构。
- 使用统一颜色函数为 Progress 指示条设置填充色。
- 保留现有阶段 Badge 和旅程名称。
- 增加或保留可见百分比文本，使当前进度不只由条长度表达。
- 进度条继续使用紧凑高度；不增加 hover 卡片整体宽度。
- `aria-label` 同时包含旅程名称和百分比。

客户管理表格中的状态 Badge、hover 打开方式、旅程选择和“查看全部业务旅程”行为不变。

## 6. 组件与文件边界

### 修改

- `CRM-Client/src/utils/dealJourney.ts`
  - 增加百分比颜色类型和映射函数。
  - 保持现有阶段百分比映射不变。
- `CRM-Client/src/components/ui/progress/Progress.vue`
  - 增加可选的指示条 class / 属性。
  - 默认行为继续使用 `bg-primary`。
- `CRM-Client/src/components/business-journey/businessJourneyListFields.ts`
  - 在当前阶段后注册 `progress` 展示列。
- `CRM-Client/src/components/business-journey/BusinessJourneyTableView.vue`
  - 渲染当前进度单元格。
- `CRM-Client/src/components/customer/CustomerDealJourneyHoverCard.vue`
  - 接入统一颜色映射和百分比显示。
- 对应 utility / 组件测试。

### 不修改

- 后端 schema、API、数据库和 migration。
- `BusinessJourneyBoardView.vue` 的卡片布局与阶段视觉。
- 其他 Progress 调用方的业务逻辑和默认颜色。
- 全局颜色 token；仅复用现有 shadcn/Tailwind 色阶。

## 7. 数据流与错误处理

数据流保持单向且无额外请求：

```text
DealJourney.current_board_stage
  → dealJourneyProgressPercent(stage)
  → progress color class
  → Progress + percentage text
```

前端 Zod schema 继续限制阶段枚举。正常渲染不会收到未知阶段；若工具层需要防御性处理，不得用静默的错误百分比覆盖接口校验错误。缺失的金额、产品等现有字段回退行为不变。

## 8. 验证与验收

### 单元与组件验证

1. 阶段百分比映射保持现有八个断言。
2. 颜色函数覆盖至少以下边界：`0`、`10`、`11`、`20`、`21`、`30`、`31`、`40`、`41`、`50`、`51`、`60`、`61`、`70`、`71`、`80`、`81`、`90`、`91`、`100`。
3. 业务旅程列表确认“当前进度”列紧跟“当前阶段”，并显示百分比与对应颜色 class。
4. 客户管理 hover 确认相同阶段产生相同百分比与颜色 class。
5. 默认 `Progress` 调用方仍使用 `bg-primary`，不受业务旅程颜色逻辑影响。
6. 业务旅程字段注册表确认进度列默认可见，且不进入筛选/排序字段。

### 命令与真实界面

- 运行相关 Vitest focused tests。
- 运行 `npm run type-check` 和 `npm run lint`。
- 使用真实浏览器打开客户管理和业务旅程列表，确认：
  - 当前进度列位置正确；
  - 进度条短且百分比可读；
  - 两处相同阶段颜色一致；
  - 列表横向滚动和 hover 交互没有回归。

### 验收标准

- 业务旅程列表默认显示“当前进度”列，位置在“当前阶段”后。
- 列表和客户管理状态 hover 对同一旅程显示相同百分比、相同颜色。
- 颜色按 10% 区间使用 orange 到 blue 的十段色阶。
- `0%` 和 `100%` 边界正确。
- 其他进度条默认颜色不变。
- 无后端或数据库改动。
- 看板卡片保持现状。
- 颜色之外仍能通过阶段文字和百分比理解状态，且具备可访问标签。
