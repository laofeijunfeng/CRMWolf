# CRM-113 四个实体图表页共享骨架实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不统一实体 schema 或指标口径的前提下，为 Contract、Customer、Opportunity、Payment 四个图表页抽取共享页面骨架与交互契约，并验证四个真实入口。

**Architecture:** 新增小型无业务 schema 的 Vue primitives：页面 shell、Card frame、bucket action list、bucket Dialog。实体 ChartPage 保留 API 类型、数据转换、金额/数量/ARR/forecast 计算和 detail renderer，通过 slots/props/emits 接入共享 primitives。四个 view 继续拥有各自请求 ID，仅补齐 mode/filter/close 的 bucket 失效和子组件 reset。

**Tech Stack:** Vue 3 `<script setup>`、TypeScript、Vitest + Vue Test Utils、Vite、Playwright、现有 Card/Dialog/ChartContainer/Button 和 V2 SCSS tokens。

## Global Constraints

- 不引入巨型通用 chart schema；实体 API/schema、指标口径、bucket key、formatter、forecast、ARR 逻辑保持独立。
- 不删除已有 `Card`、`ChartContainer`、`Dialog` 复用，不重建图表系统。
- Customer donut legend 保持纯展示；可钻取图形必须有相邻键盘可达 action list；不额外把 SVG 伪装成重复 `role=button`。
- 共享按钮必须有 `type="button"`、可见 `focus-visible`、disabled 语义和不小于现有移动触达尺寸；不使用 `any`、`as any`、`@ts-ignore` 或不必要非空断言。
- 保留现有中文文案、data-testid、筛选条件、分桶范围、preview/detail 字段和事件语义，除非为焦点/失效契约所必需。
- mode/filter 变化必须关闭 bucket 并使旧 bucket 请求失效；Payment 子组件必须同步清空本地 Dialog 选择。
- 不提交、不推送、不修改任务状态为待发布，直到 VERIFY 完成且收到精确口令「提测」。
- 每一步只运行定向检查；最终统一运行 lint、type-check、定向 unit tests 和真实 Playwright。

---

### Task 1: 建立共享图表 primitives

**Files:**
- Create: `CRM-Client/src/components/crmwolf/chart/ChartPageShell.vue`
- Create: `CRM-Client/src/components/crmwolf/chart/ChartCardFrame.vue`
- Create: `CRM-Client/src/components/crmwolf/chart/ChartBucketActionList.vue`
- Create: `CRM-Client/src/components/crmwolf/chart/ChartBucketDialog.vue`
- Create: `CRM-Client/src/components/crmwolf/chart/__tests__/ChartBucketActionList.test.ts`
- Create: `CRM-Client/src/components/crmwolf/chart/__tests__/ChartBucketDialog.test.ts`

**Interfaces:**
- `ChartPageShell` props: `loading: boolean`, `error: string`, `hasChart: boolean`, `refreshing?: boolean`; emits `retry`; slots `loading`, `error`, `empty`, `summary`, `default`, `inline-error`.
- `ChartCardFrame` props: `cardKey: string`, `title: string`, `description: string`, `wide?: boolean`; slots `default`, `legend`, `footer`.
- `ChartBucketActionList` props: `actions: readonly ChartBucketAction[]`, `testIdPrefix?: string`; emits `activate: [action: ChartBucketAction]`; action includes `key`, `label`, `valueLabel`, `disabled`, optional `color`, `disabledReason`.
- `ChartBucketDialog` props: `open: boolean`, `title: string`, `description?: string`, `loading: boolean`, `error: string`, `hasItems: boolean`, `canLoadMore: boolean`, `resetKey?: string | number`; emits `update:open`, `retry`, `load-more`; slots `items`, `empty`, `loading`, `error`.

- [ ] **Step 1: Add behavior tests first.** Assert action buttons preserve disabled rows, emit only for enabled actions, expose focus-visible styling hooks and `aria-label`; assert Dialog renders loading/error/items slots, emits retry/load-more, and closes through native Dialog behavior.
- [ ] **Step 2: Run only the new tests and confirm the expected missing-component failures.**
- [ ] **Step 3: Implement the four primitives using existing Card, Button, Dialog and V2 spacing/focus tokens.** Do not put entity types or API calls in these components.
- [ ] **Step 4: Run the new tests and the existing DialogContent tests.**
- [ ] **Step 5: Re-read the rendered markup and ensure no action list item is a `div` pretending to be interactive.

### Task 2: Migrate Contract and Customer chart pages

**Files:**
- Modify: `CRM-Client/src/components/contract/ContractChartPage.vue`
- Modify: `CRM-Client/src/components/customer/CustomerChartPage.vue`
- Modify: `CRM-Client/src/views/Contracts.vue`
- Modify: `CRM-Client/src/views/Customers.vue`
- Create or modify: `CRM-Client/src/components/contract/__tests__/ContractChartPage.test.ts`
- Create or modify: `CRM-Client/src/components/customer/__tests__/CustomerChartPage.test.ts`

**Interfaces:**
- Keep existing entity props/emits and chart data types. Convert existing legend/bucket visual rows to `ChartBucketActionList` models while keeping entity `openBucket` handlers.
- Add `bucketResetToken`/equivalent external reset input only if required by local selection state; preserve existing `close-bucket` emit.

- [ ] **Step 1: Add tests for enabled/disabled bucket keyboard activation, static Customer legend, and close/reset behavior before changing page templates.**
- [ ] **Step 2: Run the focused tests and confirm the new assertions fail on current markup/state behavior.**
- [ ] **Step 3: Replace only repeated shell/card/bucket/Dialog markup with primitives; leave Contract amount/count and Customer ratio/status/industry/city/month rendering in place.**
- [ ] **Step 4: Update Contract and Customer view mode/filter refresh paths to call existing `closeChartBucket()` before refreshing chart data, thereby invalidating `chartBucketRequestId`.**
- [ ] **Step 5: Run Contract/Customer focused tests and existing affected unit tests.

### Task 3: Migrate Payment chart page and synchronize Dialog reset

**Files:**
- Modify: `CRM-Client/src/components/payment/PaymentRecordChartPage.vue`
- Modify: `CRM-Client/src/components/payment/__tests__/PaymentRecordChartPage.test.ts`
- Modify: `CRM-Client/src/components/payment/__tests__/paymentRecordArr.test.ts`
- Modify: `CRM-Client/src/views/PaymentRecords.vue`

**Interfaces:**
- Preserve `arrLinePoints`, `arrCanOpen`, `arrShowsMarker`, payment-month zero bucket behavior, and matched `bucketRecords` behavior.
- Add an external `resetToken: string | number` or equivalent controlled reset prop to clear `selectedCard`/`selectedBucket`; keep existing emits and record detail events.

- [ ] **Step 1: Add a regression test proving a changed reset token closes the Dialog and clears the stale selected bucket; add keyboard action coverage without changing ARR semantics.**
- [ ] **Step 2: Run the focused test and confirm it fails before implementation.**
- [ ] **Step 3: Migrate stable card/legend/bucket/Dialog shell to shared primitives; keep month and ARR renderer code entity-local.**
- [ ] **Step 4: Increment the reset token in `PaymentRecords.vue` whenever `closeChartBucket()` runs and pass it to the chart page.**
- [ ] **Step 5: Run focused Payment tests. Preserve the existing baseline mismatch as a separately documented test-contract issue unless the new controlled Dialog flow changes its cause.

### Task 4: Migrate Opportunity chart page and normalize invalidation

**Files:**
- Modify: `CRM-Client/src/components/opportunity/OpportunityChartPage.vue`
- Modify: `CRM-Client/src/views/Opportunities.vue`
- Create or modify: `CRM-Client/src/components/opportunity/__tests__/OpportunityChartPage.test.ts`

**Interfaces:**
- Preserve `cardOrder`, `metricModeFor`, `metaFor`, `hasData`, forecast columns, `unscheduled` handling, and count/amount selection.
- Keep `bucketResetToken` as the external controlled reset mechanism and route bucket actions through the shared action list.

- [ ] **Step 1: Add tests for forecast-specific rendering remaining local, disabled bucket behavior, and reset token closing the Dialog.**
- [ ] **Step 2: Run focused tests and confirm the new behavior assertions fail on current implementation.**
- [ ] **Step 3: Migrate only stable shell/card/bucket/Dialog portions; do not model forecast as a generic distribution card.**
- [ ] **Step 4: Ensure tab/filter/mode transitions call `closeOpportunityChartBucket()` exactly once per refresh path and preserve existing request generation checks.**
- [ ] **Step 5: Run focused Opportunity tests.

### Task 5: Cross-page verification and evidence

**Files:**
- Modify only as needed after verification: affected chart/view/test files.
- Create: `.xwing-task/crmwolf/evidence/` PNGs and verification notes.
- Create: `.xwing-task/crmwolf/review-report.md`

- [ ] **Step 1: Run the complete affected unit-test set and record pass/fail counts, including any pre-existing baseline mismatch.**
- [ ] **Step 2: Run `npm run lint` and `npm run type-check`; fix all introduced diagnostics.**
- [ ] **Step 3: Start the actual frontend/backend environment required by the repository; use repository Playwright tests or a temporary test under the existing `tests/e2e` harness to visit `/contracts`, `/customers`, `/opportunities`, `/payments/records`.**
- [ ] **Step 4: Verify chart mode switch, keyboard bucket entry, disabled rows, Dialog open/retry/load-more/close focus return, return to entity list, responsive no-horizontal-scroll at narrow viewport.**
- [ ] **Step 5: Save screenshots under `.xwing-task/crmwolf/evidence/` and write the review report with exact commands and outputs.**
- [ ] **Step 6: Perform final code review against the approved idea; do not commit or push before the separate `提测` gate.
