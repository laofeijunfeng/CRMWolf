# 实现状态

> 本文档仅记录已验证的实现状态，不包含预估数量或未实现的工具引用。

---

## 一、设计令牌

| 项目 | 状态 | 验证日期 |
|------|------|----------|
| shadcn CSS variables | 已集中到 `src/styles/base.css` | 2026-07-28 |
| V2 兼容变量定义 | 已定义 | 2026-07-28 |
| Tailwind 配置 | 已消费 CSS variables | 2026-07-28 |
| Stylelint 规则 | 已配置 | 2026-07-14 |

---

## 二、shadcn-vue 组件

| 组件 | 状态 | 验证日期 |
|------|------|----------|
| `Button` | 已实现 | 2026-07-14 |
| `Input` | 已实现 | 2026-07-14 |
| `Card` 系列 | 已实现 | 2026-07-14 |
| `Table` 系列 | 已实现 | 2026-07-14 |
| `Tabs` 系列 | 已实现 | 2026-07-14 |
| `Alert` 系列 | 已实现 | 2026-07-14 |
| `Form` | 已实现 | 2026-07-14 |
| `Label` | 已实现 | 2026-07-14 |
| `Toast` | 已实现 | 2026-07-14 |

---

## 三、迁移进度

| 项目 | 状态 | 验证日期 |
|------|------|----------|
| 设计令牌系统 | slate 中性色 + Tailwind blue 主强调色已收拢 | 2026-07-28 |
| 基础组件库 | 目标状态，尚未在现有组件中全面落地 | 2026-07-14 |
| 导航组件库 | 目标状态，尚未在现有组件中全面落地 | 2026-07-14 |
| 页面迁移 | 目标状态，尚未在现有组件中全面落地 | 2026-07-14 |

---

## 四、迁移治理基线

| 项目 | 状态 | 验证日期 |
|------|------|----------|
| Element Plus 运行时依赖 | `package.json` 未发现依赖 | 2026-09-04 |
| Element Plus 组件调用 | 核心源码审计未发现真实 `el-*` 模板调用 | 2026-09-04 |
| P2-04 文件级迁移台账 | 已建立，详见 [P2-04 台账](./p2-pkg-04-inventory.md) | 2026-09-04 |
| P2-04 新增代码门禁 | 已提供 `npm run lint:design-system` | 2026-09-04 |

Element Plus 迁移文档保留为历史背景，不代表当前仍存在对应运行时依赖。设计系统治理优先关注新增 raw color、旧 Token、状态组合分叉以及共享组件契约。

## 五、P2-04 文件级验证证据

| 入口 | 当前证据 | 状态 | 验证日期 |
|------|----------|------|----------|
| `MetricCard` | 边框、背景、tone 和文本已改用 shadcn CSS variables | 已验证 | 2026-09-04 |
| `TopBarTabs` | 激活、hover、focus、危险操作改用语义 CSS variables | 已验证 | 2026-09-04 |
| `DataViewStatePanel` + `PaymentPlanDetailContent` | loading/error/empty/ready 组合已接入，保留回款动作 | 已验证 | 2026-09-04 |
| `StatusBadge` + `ApprovalStatusBadge` | 生命周期/审批契约有未知状态兜底和组件测试 | 已验证 | 2026-09-04 |
| `SalesDashboard` | 页面 UI 边框、错误提示和分隔线已迁移；图表序列色保留登记例外 | 部分验证 | 2026-09-04 |
| `AppLayout` | 壳层背景、分隔线、标题、focus 和危险操作改用 shadcn CSS variables | 已验证 | 2026-09-04 |
| `AccountSettings` | 账户页面 loading/error/empty/ready 统一由 `DataViewStatePanel` 承载，保留密码与飞书授权动作 | 已验证 | 2026-09-04 |
| `CustomerOpportunityHoverCard` | 客户商机浮层 loading/error/empty/ready 统一由 `DataViewStatePanel` 承载，保留预览与跳转动作；商机阶段蓝色标签例外登记为 `DS-EX-003` | 已验证 | 2026-09-04 |

验证命令：`npm run type-check`、`npm run build`、`npm run test:governance`、`npm run test:unit -- --run tests/components/StatusBadge.spec.ts tests/components/ApprovalStatusBadge.spec.ts tests/components/DataViewStatePanel.spec.ts`、`npm run lint:design-system -- --worktree`。详细字段以 [P2-04 台账](./p2-pkg-04-inventory.md) 为准。

---

**最后更新**：2026-09-04
