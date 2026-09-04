# P2-04 设计系统治理迁移台账

本台账对应 `docs/ux/p2-packages/p2-pkg-04-design-system-governance-trd.md`，机器可读明细见 [`p2-pkg-04-inventory.json`](./p2-pkg-04-inventory.json)，例外见 [`p2-pkg-04-exceptions.json`](./p2-pkg-04-exceptions.json)。

## 使用规则

- `implemented-compatible` 表示能力已经存在，本期只保留兼容边界和验证证据，不重复建设。
- `pending` 表示已定位的迁移项，必须先完成对应批次再更新状态。
- `exception-registered` 表示有意保留的可视化或兼容实现，必须有负责人和复核日期。
- 新增样式通过 `CRM-Client` 的 `npm run lint:design-system` 检查；存量全量盘点使用 `npm run lint:design-system:all`。
- DS-12 的商机阶段蓝色标签例外见 `DS-EX-003`，不等同于生命周期状态徽章。

## 首批入口

| ID | 范围 | 负责人 | 批次 | 当前状态 | 主要风险 |
| --- | --- | --- | --- | --- | --- |
| DS-01 | AppLayout | frontend-platform | P2-04-05 | implemented-compatible | 主题回归 |
| DS-02 | SalesDashboard 图表序列色 | frontend-platform | P2-04-05 | exception-registered | 可视化回归 |
| DS-03 | MetricCard | frontend-platform | P2-04-05 | implemented-compatible | 主题回归 |
| DS-04 | TopBarTabs | frontend-platform | P2-04-05 | implemented-compatible | 导航回归 |
| DS-05 | PaymentPlanDetailContent 状态组合 | frontend-platform | P2-04-03/05 | implemented-compatible | 详情流程回归 |
| DS-06 | DataTable 兼容契约 | frontend-platform | P2-04-02/06 | implemented-compatible | 列表滚动回归 |
| DS-07 | StatusBadge | frontend-platform | P2-04-04 | implemented-compatible | 状态展示回归 |
| DS-08 | ApprovalStatusBadge | frontend-platform | P2-04-04 | implemented-compatible | 审批语义回归 |
| DS-09 | ErrorState | frontend-platform | P2-04-03 | implemented-compatible | 无障碍回归 |
| DS-10 | LoadingSkeleton | frontend-platform | P2-04-03/06 | implemented-compatible | 布局跳动 |
| DS-11 | AccountSettings 状态组合 | frontend-platform | P2-04-03/06 | implemented-compatible | 设置流程回归 |
| DS-12 | CustomerOpportunityHoverCard 状态组合 | frontend-platform | P2-04-03/06 | exception-registered | 浮层预览与阶段标签回归 |

## 更新要求

每次迁移完成后同步更新 JSON 中的 `status`、`verification`、`lastVerified`，并运行设计系统文档检查。不得用“全站已完成”替代文件级证据，也不得为了通过门禁删除合理的图表色板或 DataTable 兼容参数。
