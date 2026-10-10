# Business Journey Progress Color Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在业务旅程列表中新增默认可见的“当前进度”列，并让列表与客户管理状态 hover 使用同一套阶段百分比和进度颜色。

**Architecture:** 保留 `dealJourneyProgressPercent()` 作为唯一阶段到百分比的来源，在同一工具文件中增加百分比到 Tailwind 填充 class 的纯函数。通用 `Progress` 只增加可选的 `indicatorClass` 属性，未传入时仍使用 `bg-primary`；业务旅程列表和客户 hover 显式传入共享颜色，其他进度条不改变。列表的 `progress` 只注册为 display-only decoration 字段，不进入后端筛选、排序或导出。

**Tech Stack:** Vue 3 `<script setup>`, TypeScript 5.7, reka-ui `Progress`, Tailwind CSS, Vue Test Utils, Vitest, ESLint, vue-tsc, Node design-system governance checks, Playwright-capable Chromium.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-10-09-business-journey-progress-color-design.md`.
- 不修改后端 schema、API、数据库、migration 或任何业务旅程后端字段。
- 不修改 `CRM-Client/src/components/business-journey/BusinessJourneyBoardView.vue` 的行为、卡片布局或阶段视觉。
- 保持现有八个阶段百分比映射：`early_communication=14`、`active_progress=29`、`closing_soon=43`、`contract_processing=57`、`payment_processing=71`、`invoice_processing=86`、`completed=100`、`lost=0`。
- `progress` 字段必须紧跟 `current_board_stage`，默认可见，并继续受现有字段配置隐藏/恢复。
- `progress` 是派生展示字段，显式关闭筛选、排序和导出，并提供筛选/排序关闭原因。
- 颜色区间必须精确为 `0–10 orange`、`11–20 amber`、`21–30 yellow`、`31–40 lime`、`41–50 green`、`51–60 emerald`、`61–70 teal`、`71–80 cyan`、`81–90 sky`、`91–100 blue`，对应 `bg-<color>-500`。
- 阶段文字和百分比文字必须保留；颜色不能作为唯一状态信号；两处必须有包含旅程名和百分比的可访问标签。
- 通用 `Progress` 未传 `indicatorClass` 时必须继续渲染 `bg-primary`；审批、回款、上传等既有调用方不改业务逻辑或调用参数。
- 不新增 `any`、`as any` 或 `@ts-ignore`；保留 typed Vue props/emits。
- 颜色 class 必须以完整字面量出现，不能用动态字符串拼接，以保证 Tailwind 静态发现。
- 保留工作区所有无关 dirty changes；每次提交只暂存本计划列出的文件。
- 生产代码遵循红—绿：先写测试、运行确认失败，再写最小实现；不要在中途运行项目级 lint、type-check 或完整测试套件。

## File Structure

- Modify `CRM-Client/src/utils/dealJourney.ts` — 保持阶段百分比映射，新增百分比区间到颜色 class 的 typed helper。
- Modify `CRM-Client/src/utils/__tests__/dealJourney.test.ts` — 保留八个阶段映射断言，增加全部指定边界的颜色断言。
- Modify `CRM-Client/src/components/ui/progress/Progress.vue` — 增加可选 `indicatorClass` typed prop，并只在传入时覆盖 indicator 背景色。
- Create `CRM-Client/src/components/ui/progress/__tests__/Progress.test.ts` — 锁定默认 `bg-primary` 和自定义 indicator class 行为。
- Modify `CRM-Client/src/components/business-journey/businessJourneyListFields.ts` — 在阶段字段后注册 display-only `progress` 列。
- Modify `CRM-Client/tests/components/BusinessJourneyTableView.spec.ts` — 锁定字段投影、列顺序、29% 展示、黄色填充和可访问标签。
- Modify `CRM-Client/src/components/business-journey/BusinessJourneyTableView.vue` — 渲染短进度条与百分比，不改变行点击和其他 slot。
- Modify `CRM-Client/tests/components/CustomerDealJourneyHoverCard.spec.ts` — mock `indicatorClass`，锁定 43%/100% 的颜色、可见百分比和现有 aria-label。
- Modify `CRM-Client/src/components/customer/CustomerDealJourneyHoverCard.vue` — 接入共享颜色 helper，并在现有紧凑进度条旁显示百分比。
- Modify `CRM-Docs/design-system/migration/p2-pkg-04-exceptions.json` — 若增量治理扫描命中新增量化进度填充 token，登记只针对 `dealJourney.ts` 和十个完整 token 的精确例外。

---

### Task 1: Add the shared journey progress color helper

**Files:**
- Modify: `CRM-Client/src/utils/__tests__/dealJourney.test.ts`
- Modify: `CRM-Client/src/utils/dealJourney.ts`
- Modify: `CRM-Docs/design-system/migration/p2-pkg-04-exceptions.json` only if the governance scan reports the new literal status-color tokens

**Interfaces:**
- Consumes: existing `DealJourneyBoardStage` and `dealJourneyProgressPercent(stage: DealJourneyBoardStage): number`.
- Produces: `DealJourneyProgressColorClass` and `dealJourneyProgressColorClass(percent: number): DealJourneyProgressColorClass`.
- Does not change `DEAL_JOURNEY_PROGRESS_PERCENT`, `dealJourneyProgressPercent`, stage labels, schemas, or API contracts.

- [ ] **Step 1: Add the failing boundary test**

Extend the existing import in `CRM-Client/src/utils/__tests__/dealJourney.test.ts`:

```ts
import {
  DEAL_JOURNEY_BOARD_STAGE_LABELS,
  dealJourneyProgressColorClass,
  dealJourneyProgressPercent,
  isDealJourneyPublicId
} from '@/utils/dealJourney'
```

Add this test after the existing `maps board stages to hover progress` test:

```ts
  it.each([
    [0, 'bg-orange-500'],
    [10, 'bg-orange-500'],
    [11, 'bg-amber-500'],
    [20, 'bg-amber-500'],
    [21, 'bg-yellow-500'],
    [30, 'bg-yellow-500'],
    [31, 'bg-lime-500'],
    [40, 'bg-lime-500'],
    [41, 'bg-green-500'],
    [50, 'bg-green-500'],
    [51, 'bg-emerald-500'],
    [60, 'bg-emerald-500'],
    [61, 'bg-teal-500'],
    [70, 'bg-teal-500'],
    [71, 'bg-cyan-500'],
    [80, 'bg-cyan-500'],
    [81, 'bg-sky-500'],
    [90, 'bg-sky-500'],
    [91, 'bg-blue-500'],
    [100, 'bg-blue-500']
  ] as const)('maps %s percent to the expected progress color', (percent, expected) => {
    expect(dealJourneyProgressColorClass(percent)).toBe(expected)
  })
```

- [ ] **Step 2: Run the utility test and confirm RED**

Run:

```bash
cd CRM-Client && npx vitest run src/utils/__tests__/dealJourney.test.ts
```

Expected: FAIL during module import or test execution because `dealJourneyProgressColorClass` is not exported yet. The pre-existing eight stage percentage assertions must remain present; do not remove or rewrite them.

- [ ] **Step 3: Implement the minimal typed helper**

Append the following type and function after `dealJourneyProgressPercent()` in `CRM-Client/src/utils/dealJourney.ts`; leave the existing percentage map unchanged:

```ts
export type DealJourneyProgressColorClass =
  | 'bg-orange-500'
  | 'bg-amber-500'
  | 'bg-yellow-500'
  | 'bg-lime-500'
  | 'bg-green-500'
  | 'bg-emerald-500'
  | 'bg-teal-500'
  | 'bg-cyan-500'
  | 'bg-sky-500'
  | 'bg-blue-500'

export function dealJourneyProgressColorClass(percent: number): DealJourneyProgressColorClass {
  if (percent <= 10) return 'bg-orange-500'
  if (percent <= 20) return 'bg-amber-500'
  if (percent <= 30) return 'bg-yellow-500'
  if (percent <= 40) return 'bg-lime-500'
  if (percent <= 50) return 'bg-green-500'
  if (percent <= 60) return 'bg-emerald-500'
  if (percent <= 70) return 'bg-teal-500'
  if (percent <= 80) return 'bg-cyan-500'
  if (percent <= 90) return 'bg-sky-500'
  return 'bg-blue-500'
}
```

The helper intentionally receives the already validated integer stage percentage. It must not introduce a fallback percentage, change API validation, or generate class names dynamically.

- [ ] **Step 4: Run the utility test and confirm GREEN**

Run:

```bash
cd CRM-Client && npx vitest run src/utils/__tests__/dealJourney.test.ts
```

Expected: all existing stage mapping, public-id, label, and new color-boundary tests pass.

- [ ] **Step 5: Register only the required design-system exception if governance flags the helper**

Run the focused governance test/inspection after the helper exists:

```bash
cd CRM-Client && node --input-type=module -e "import { readFileSync } from 'node:fs'; import { inspectContent } from './scripts/check-design-system-governance.mjs'; const lines = readFileSync('src/utils/dealJourney.ts', 'utf8').split('\\n'); const violations = inspectContent('CRM-Client/src/utils/dealJourney.ts', lines); console.log(JSON.stringify(violations)); process.exit(violations.length ? 1 : 0)"
```

```json
{
  "id": "DS-EX-006",
  "category": "status-color",
  "files": [
    "CRM-Client/src/utils/dealJourney.ts"
  ],
  "match": "\\b(?:bg-orange-500|bg-amber-500|bg-yellow-500|bg-lime-500|bg-green-500|bg-emerald-500|bg-teal-500|bg-cyan-500|bg-sky-500|bg-blue-500)\\b",
  "reason": "业务旅程进度条使用十段量化进度色阶；颜色与阶段百分比一一对应，必须保留完整 Tailwind 字面量以支持静态发现，并由阶段文字和百分比提供非颜色状态线索。",
  "owner": "frontend",
  "reviewDate": "2026-12-21",
  "status": "active"
}
```

Set the exception file's `lastVerified` to `2026-10-09` when this entry is added. Do not broaden an existing color regex, add unrelated files, or exempt the entire color family.

- [ ] **Step 6: Commit the utility contract**

```bash
git add CRM-Client/src/utils/dealJourney.ts CRM-Client/src/utils/__tests__/dealJourney.test.ts CRM-Docs/design-system/migration/p2-pkg-04-exceptions.json
git commit -m "feat: add business journey progress colors"
```

If the governance file was not changed, omit it from `git add`; never stage unrelated worktree changes.

---

### Task 2: Extend `Progress` with an optional indicator class

**Files:**
- Create: `CRM-Client/src/components/ui/progress/__tests__/Progress.test.ts`
- Modify: `CRM-Client/src/components/ui/progress/Progress.vue`

**Interfaces:**
- Consumes: reka-ui `ProgressRootProps`, existing `class` prop, and `cn()`.
- Produces: optional `indicatorClass?: HTMLAttributes['class']`; existing callers remain source-compatible.
- The root still delegates all `ProgressRootProps` except the two wrapper-only props `class` and `indicatorClass`.

- [ ] **Step 1: Write the failing default/custom indicator tests**

Create `CRM-Client/src/components/ui/progress/__tests__/Progress.test.ts` with:

```ts
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import Progress from '../Progress.vue'

describe('Progress indicator classes', () => {
  it('keeps bg-primary as the default indicator fill', () => {
    const wrapper = mount(Progress, { props: { modelValue: 42 } })

    expect(wrapper.get('[role="progressbar"] > div').classes()).toContain('bg-primary')
  })

  it('uses a caller-provided indicator class without the default fill', () => {
    const wrapper = mount(Progress, {
      props: {
        modelValue: 42,
        indicatorClass: 'bg-yellow-500'
      }
    })

    const indicator = wrapper.get('[role="progressbar"] > div')
    expect(indicator.classes()).toContain('bg-yellow-500')
    expect(indicator.classes()).not.toContain('bg-primary')
  })
})
```

- [ ] **Step 2: Run the component test and confirm RED**

Run:

```bash
cd CRM-Client && npx vitest run src/components/ui/progress/__tests__/Progress.test.ts
```

Expected: the default test may pass against the existing implementation, while the custom indicator test fails because `indicatorClass` is not an accepted/used prop. Treat the suite as RED until both assertions pass after the implementation.

- [ ] **Step 3: Add the typed prop and class merge**

Replace the existing prop declaration and delegated-props line in `CRM-Client/src/components/ui/progress/Progress.vue` with:

```ts
const props = withDefaults(
  defineProps<ProgressRootProps & {
    class?: HTMLAttributes['class']
    indicatorClass?: HTMLAttributes['class']
  }>(),
  {
    modelValue: 0,
  },
)

const delegatedProps = reactiveOmit(props, 'class', 'indicatorClass')
```

Replace the indicator element with:

```vue
    <ProgressIndicator
      :class="cn('h-full w-full flex-1 bg-primary transition-all', props.indicatorClass)"
      :style="`transform: translateX(-${100 - (props.modelValue ?? 0)}%);`"
    />
```

Keep the existing root class merge, `omitUndefined(delegatedProps)`, model default, and transform behavior unchanged. `cn()` must remove the default background utility when a caller supplies another background utility while preserving all non-background indicator classes.

- [ ] **Step 4: Run the component test and confirm GREEN**

Run:

```bash
cd CRM-Client && npx vitest run src/components/ui/progress/__tests__/Progress.test.ts
```

Expected: both default and custom indicator tests pass. Existing callers must not be changed in this task.

- [ ] **Step 5: Commit the generic component contract**

```bash
git add CRM-Client/src/components/ui/progress/Progress.vue CRM-Client/src/components/ui/progress/__tests__/Progress.test.ts
git commit -m "feat: allow custom progress indicator colors"
```

---

### Task 3: Register the derived display-only progress column

**Files:**
- Modify: `CRM-Client/src/components/business-journey/businessJourneyListFields.ts`
- Modify: `CRM-Client/tests/components/BusinessJourneyTableView.spec.ts`

**Interfaces:**
- Consumes: `defineListFields()` and `projectListFieldCatalog()` defaults.
- Produces: a `progress` field with label `当前进度`, width `96px`, default visibility, no filter/sort/export, and no new response property.
- Later table rendering reads `row.current_board_stage`; it must not expect `row.progress` from `BusinessJourneyListItem`.

- [ ] **Step 1: Add the failing field registration contract test**

Add this import to `CRM-Client/tests/components/BusinessJourneyTableView.spec.ts`:

```ts
import { projectListFieldCatalog } from '@/components/crmwolf/listFieldCatalog'
```

Add this test before the existing stage-palette table:

```ts
  it('registers progress immediately after stage as a default-visible display-only field', () => {
    const fields = createBusinessJourneyListFields([])

    expect(fields.map(field => field.key)).toEqual([
      'name',
      'customer_name',
      'current_board_stage',
      'progress',
      'primary_opportunity_name',
      'product_name',
      'amount',
      'purchase_type',
      'owner_id',
      'last_event_at',
      'expected_closing_date'
    ])

    expect(fields[3]).toMatchObject({
      key: 'progress',
      label: '当前进度',
      role: 'decoration',
      column: { width: '96px' },
      filter: false,
      filterDisabledReason: '当前进度由当前阶段派生，不支持筛选',
      sort: false,
      sortDisabledReason: '当前进度由当前阶段派生，不支持排序',
      export: false
    })

    const projected = projectListFieldCatalog(fields)
    expect(projected.columns.map(column => column.key)).toContain('progress')
    expect(projected.filterFields.map(field => field.key)).not.toContain('progress')
    expect(projected.sortFields.map(field => field.key)).not.toContain('progress')
    expect(projected.exportFields.map(field => field.fieldKey)).not.toContain('progress')
  })
```

- [ ] **Step 2: Run the field contract test and confirm RED**

Run:

```bash
cd CRM-Client && npx vitest run tests/components/BusinessJourneyTableView.spec.ts -t "registers progress immediately after stage"
```

Expected: FAIL because the current catalog has no `progress` key and `primary_opportunity_name` currently follows `current_board_stage`.

- [ ] **Step 3: Add the display-only field after `current_board_stage`**

In `CRM-Client/src/components/business-journey/businessJourneyListFields.ts`, insert this exact object immediately after the `current_board_stage` definition and before `primary_opportunity_name`:

```ts
    {
      key: 'progress',
      label: '当前进度',
      role: 'decoration',
      column: { width: '96px' },
      filter: false,
      filterDisabledReason: '当前进度由当前阶段派生，不支持筛选',
      sort: false,
      sortDisabledReason: '当前进度由当前阶段派生，不支持排序',
      export: false
    },
```

Do not add `type`, `options`, `apiKey`, or a schema field. `role: 'decoration'` prevents business-column defaults, while explicit false values document the contract and keep the field out of all query/export projections.

- [ ] **Step 4: Run the field contract and existing table tests**

Run:

```bash
cd CRM-Client && npx vitest run tests/components/BusinessJourneyTableView.spec.ts
```

Expected: the new field projection test and all existing table layout, row-click, date, and stage-palette tests pass.

- [ ] **Step 5: Commit the field catalog contract**

```bash
git add CRM-Client/src/components/business-journey/businessJourneyListFields.ts CRM-Client/tests/components/BusinessJourneyTableView.spec.ts
git commit -m "feat: register business journey progress column"
```

---

### Task 4: Render the progress cell in the business-journey table

**Files:**
- Modify: `CRM-Client/src/components/business-journey/BusinessJourneyTableView.vue`
- Modify: `CRM-Client/tests/components/BusinessJourneyTableView.spec.ts`

**Interfaces:**
- Consumes: `Progress` from `@/components/crmwolf`, `dealJourneyProgressPercent()`, and `dealJourneyProgressColorClass()`.
- Produces: a compact `progress` cell whose fixture stage `active_progress` renders `29%` and `bg-yellow-500`.
- Preserves `DataTable` row-interactive behavior, name click handling, all existing slots, and the board view (which is not touched).

- [ ] **Step 1: Add the failing table rendering test**

Append this test to the `BusinessJourneyTableView layout` suite after the field registration test:

```ts
  it('renders the derived percentage, shared color, compact bar, and accessible label', () => {
    const wrapper = mountJourneyTable([journeyFixture])
    const progressCell = wrapper.get('[data-testid="business-journey-progress"]')
    const progress = progressCell.get('[role="progressbar"]')
    const indicator = progressCell.get('[role="progressbar"] > div')

    expect(progressCell.attributes('aria-label')).toBe('华东续约旅程 当前进度 29%')
    expect(progress.attributes('aria-label')).toBe('华东续约旅程 当前进度 29%')
    expect(progressCell.text()).toContain('29%')
    expect(progressCell.classes()).toContain('items-center')
    expect(progress.classes()).toContain('h-1.5')
    expect(indicator.classes()).toContain('bg-yellow-500')
  })
```

- [ ] **Step 2: Run the rendering test and confirm RED**

Run:

```bash
cd CRM-Client && npx vitest run tests/components/BusinessJourneyTableView.spec.ts -t "renders the derived percentage"
```

Expected: FAIL because `BusinessJourneyTableView.vue` has no `cell-progress` slot and therefore no progress wrapper, percentage, label, or custom indicator class.

- [ ] **Step 3: Add typed progress helpers and the `cell-progress` slot**

Update the CRMWolf import in `BusinessJourneyTableView.vue`:

```ts
import { AmountText, Badge, DataTable, Progress, StatusBadge } from '@/components/crmwolf'
```

Add this utility import with the other imports:

```ts
import {
  dealJourneyProgressColorClass,
  dealJourneyProgressPercent
} from '@/utils/dealJourney'
```

Add these typed helpers before `</script>`:

```ts
const getJourneyProgressPercent = (row: BusinessJourneyListItem): number =>
  dealJourneyProgressPercent(row.current_board_stage)

const getJourneyProgressColorClass = (row: BusinessJourneyListItem): string =>
  dealJourneyProgressColorClass(getJourneyProgressPercent(row))

const getJourneyProgressLabel = (row: BusinessJourneyListItem): string =>
  `${row.name} 当前进度 ${getJourneyProgressPercent(row)}%`
```

Insert this slot immediately after `#cell-current_board_stage` and before `#cell-primary_opportunity_name`:

```vue
    <template #cell-progress="{ row }">
      <div
        class="flex min-w-0 items-center gap-2"
        data-testid="business-journey-progress"
        role="group"
        :aria-label="getJourneyProgressLabel(row)"
      >
        <Progress
          :model-value="getJourneyProgressPercent(row)"
          :indicator-class="getJourneyProgressColorClass(row)"
          class="h-1.5 min-w-0 flex-1 bg-secondary"
          :aria-label="getJourneyProgressLabel(row)"
        />
        <span class="shrink-0 tabular-nums text-xs text-muted-foreground">
          {{ getJourneyProgressPercent(row) }}%
        </span>
      </div>
    </template>
```

The wrapper label and native progressbar label intentionally use the same journey name/percentage contract; the adjacent percentage remains visible to sighted users and is not color-dependent. Do not add `row.progress` to the API/schema type.

- [ ] **Step 4: Run the focused table suite and confirm GREEN**

Run:

```bash
cd CRM-Client && npx vitest run tests/components/BusinessJourneyTableView.spec.ts
```

Expected: all table tests pass, including 29%/yellow rendering, field order/projection, row click, date, height, and stage palette. Confirm the existing name click still emits exactly one `row-click` event.

- [ ] **Step 5: Commit the table rendering**

```bash
git add CRM-Client/src/components/business-journey/BusinessJourneyTableView.vue CRM-Client/tests/components/BusinessJourneyTableView.spec.ts
git commit -m "feat: show business journey progress in table"
```

---

### Task 5: Apply the shared color and visible percentage to customer hover

**Files:**
- Modify: `CRM-Client/src/components/customer/CustomerDealJourneyHoverCard.vue`
- Modify: `CRM-Client/tests/components/CustomerDealJourneyHoverCard.spec.ts`

**Interfaces:**
- Consumes: the same `dealJourneyProgressPercent()` and `dealJourneyProgressColorClass()` used by the table.
- Produces: closing-soon `43%` with `bg-green-500`, completed `100%` with `bg-blue-500`, visible percentage text, and the existing exact aria-labels.
- Preserves card width `w-[460px]`, compact `h-1.5`, journey selection, stage Badge, preview filtering, and “查看全部业务旅程”.

- [ ] **Step 1: Update the Progress mock and add failing color/percentage assertions**

Replace the mocked `Progress` component in `CRM-Client/tests/components/CustomerDealJourneyHoverCard.spec.ts` with:

```ts
  Progress: defineComponent({
    name: 'Progress',
    props: {
      modelValue: Number,
      indicatorClass: String
    },
    setup: (props, { attrs }) => () => h('div', {
      ...attrs,
      'data-progress': String(props.modelValue),
      'data-indicator-class': props.indicatorClass
    }),
  }),
```

In `loads deal journeys on first open and previews name, amount, progress, and stage badge`, extend the existing first-item assertions after `expect(item.get('[data-progress="43"]').exists()).toBe(true)`:

```ts
    const firstProgress = item.get('[data-progress="43"]')
    expect(firstProgress.attributes('data-indicator-class')).toBe('bg-green-500')
    expect(item.text()).toContain('43%')
    expect(firstProgress.attributes('aria-label')).toBe('企业 CRM 升级项目 旅程进度 43%')
```

Extend the completed test after `const progress = wrapper.get('[data-progress="100"]')`:

```ts
    expect(progress.attributes('data-indicator-class')).toBe('bg-blue-500')
    expect(wrapper.text()).toContain('100%')
```

- [ ] **Step 2: Run the hover tests and confirm RED**

Run:

```bash
cd CRM-Client && npx vitest run tests/components/CustomerDealJourneyHoverCard.spec.ts
```

Expected: the updated color and visible-percentage assertions fail because the component currently passes no `indicatorClass` and renders no standalone percentage text. Existing loading, selection, filtering, footer, and aria-label assertions must remain intact.

- [ ] **Step 3: Add typed helper functions and the shared color binding**

Update the utility import in `CustomerDealJourneyHoverCard.vue`:

```ts
import {
  dealJourneyProgressColorClass,
  dealJourneyProgressPercent,
  type DealJourneyBoardStage
} from '@/utils/dealJourney'
```

Add these helpers after `getProductName()`:

```ts
const getJourneyProgressPercent = (journey: DealJourney): number =>
  dealJourneyProgressPercent(journey.current_board_stage)

const getJourneyProgressColorClass = (journey: DealJourney): string =>
  dealJourneyProgressColorClass(getJourneyProgressPercent(journey))

const getJourneyProgressLabel = (journey: DealJourney): string =>
  `${journey.name} 旅程进度 ${getJourneyProgressPercent(journey)}%`
```

Replace the existing single `Progress` element with this compact wrapper, keeping it in the same position before the stage Badge:

```vue
                  <div class="mt-wolf-md flex items-center gap-wolf-sm">
                    <Progress
                      :model-value="getJourneyProgressPercent(journey)"
                      :indicator-class="getJourneyProgressColorClass(journey)"
                      class="h-1.5 min-w-0 flex-1 bg-wolf-bg-card"
                      :aria-label="getJourneyProgressLabel(journey)"
                    />
                    <span class="shrink-0 tabular-nums text-wolf-caption text-wolf-text-tertiary-v2">
                      {{ getJourneyProgressPercent(journey) }}%
                    </span>
                  </div>
```

Do not change `content-class="... w-[460px] ..."`, the stage Badge, button handlers, or preview filtering. Keep the exact label format `旅程进度` so the existing completed aria assertion remains stable.

- [ ] **Step 4: Run the hover suite and confirm GREEN**

Run:

```bash
cd CRM-Client && npx vitest run tests/components/CustomerDealJourneyHoverCard.spec.ts
```

Expected: all hover tests pass, including the first journey's 43% green indicator, visible percentage and exact label, completed 100% blue indicator and label, selection, footer, empty/error behavior, and request de-duplication.

- [ ] **Step 5: Commit the hover rendering**

```bash
git add CRM-Client/src/components/customer/CustomerDealJourneyHoverCard.vue CRM-Client/tests/components/CustomerDealJourneyHoverCard.spec.ts
git commit -m "feat: color customer journey hover progress"
```

---

### Task 6: Run focused governance and frontend verification

**Files:**
- No new production files.
- Verify the files listed in Tasks 1–5; only modify the governance exception file if the exact scan requires it.

**Interfaces:**
- Consumes: completed utility, Progress, field catalog, table, hover, and focused tests.
- Produces: evidence that the feature is typed, lint-clean, governance-compliant, and does not regress the relevant frontend tests.

- [ ] **Step 1: Run the complete focused Vitest command**

Run:

```bash
cd CRM-Client && npx vitest run \
  src/utils/__tests__/dealJourney.test.ts \
  src/components/ui/progress/__tests__/Progress.test.ts \
  tests/components/BusinessJourneyTableView.spec.ts \
  tests/components/CustomerDealJourneyHoverCard.spec.ts \
  src/components/crmwolf/__tests__/listFieldCatalog.test.ts
```

Expected: all selected tests pass. This covers all ten color boundaries, all eight stage percentages, generic Progress default/custom behavior, list projection rules, table rendering, hover rendering, and existing catalog contracts.

- [ ] **Step 2: Run frontend type-check and lint**

Run:

```bash
cd CRM-Client && npm run type-check
cd CRM-Client && npm run lint
```

Expected: both commands exit successfully with no new TypeScript or ESLint errors. In particular, no untyped prop access, implicit `any`, or stale unused import remains.

- [ ] **Step 3: Run governance unit tests and incremental governance inspection**

Run:

```bash
cd CRM-Client && npm run test:governance
cd CRM-Client && npm run lint:design-system -- --worktree
```

Expected: governance unit tests pass; incremental governance reports no violations for the changed frontend files. If unrelated pre-existing dirty frontend files are reported, isolate the feature files with the exported `inspectContent()` helper, preserve those unrelated changes, and report the unrelated paths rather than broadening this feature's exception.

- [ ] **Step 4: Run the relevant full frontend unit suite**

Run:

```bash
cd CRM-Client && npm run test:unit
```

Expected: the complete existing Vitest suite passes. Do not weaken or delete unrelated tests to accommodate this feature.

- [ ] **Step 5: Confirm no backend/schema/board scope was introduced**

Inspect the final task diff only for the files listed in this plan and verify:

```text
CRM-Server/: unchanged by this feature
CRM-Client/src/schemas/dealJourney.ts: unchanged
CRM-Client/src/components/business-journey/BusinessJourneyBoardView.vue: unchanged
CRM-Client/src/components/ui/progress callers other than table/hover: unchanged
```

The result must show no new API field, no `row.progress` schema property, and no board card modification.

---

### Task 7: Verify the actual web surfaces in Chromium

**Files:**
- No source changes; browser smoke verification only.

**Interfaces:**
- Consumes: the built/dev frontend after Tasks 1–6 pass.
- Produces: visual and interaction evidence for the business-journey table and customer status hover.

- [ ] **Step 1: Start the actual frontend dev server**

From the repository root, start the service through the project process manager so it can be stopped cleanly:

```text
application: npm
args: ["run", "dev", "--", "--host", "127.0.0.1"]
cwd: CRM-Client
ready: port 5173 or the Vite Local URL printed by the process
```

Expected: Vite reports a local HTTP URL without compile errors. Keep the server running only for the smoke checks, then stop it through the process manager.

- [ ] **Step 2: Verify the business-journey table surface**

Open `http://127.0.0.1:5173/business-journeys` in Chromium and inspect the real table. Verify all of the following in the rendered page:

1. The header `当前进度` is immediately after `当前阶段`.
2. The progress cell is compact, shows a short bar and readable percentage text, and uses the expected fill class for the rendered stage.
3. The stage text remains visible beside the progress column.
4. Existing row/name click navigation still works once, and table horizontal scrolling does not clip the new cell.
5. The field configuration surface includes `当前进度`; hiding and restoring it changes only that column.
6. The field is absent from filter and sort controls, consistent with its derived display-only contract.

- [ ] **Step 3: Verify the customer status hover surface**

Open `http://127.0.0.1:5173/customers`, locate a customer with a previewable business journey, and open the status hover. Verify:

1. The card remains `w-[460px]` and the progress bar remains compact.
2. The journey name, stage Badge, visible percentage, and short colored bar are all present.
3. The same stage percentage/color as the business-journey table is visually identical.
4. The existing hover open/close, journey selection, and `查看全部业务旅程` action still work.
5. The accessibility label contains the journey name and percentage.

- [ ] **Step 4: Stop the dev server and record exact verification evidence**

Stop the named process cleanly. Record the exact Vitest, type-check, lint, governance, and browser routes/scenarios exercised. Do not claim a browser result if the actual surface was not opened.

---

## Self-review checklist

- **Spec coverage:** Tasks 1–2 cover the unchanged eight-stage mapping, all twenty exact boundary assertions, ten literal color classes, generic `Progress` opt-in coloring, and unchanged default `bg-primary`. Tasks 3–4 cover the default-visible `progress` column immediately after `current_board_stage`, 96px width, explicit filter/sort/export disablement, compact bar, visible percentage, shared color, and accessible labels. Task 5 covers the customer hover's shared color, visible percentage, exact aria-label contract, unchanged width/height/selection/footer. Tasks 6–7 cover no backend/schema/board changes, focused/full frontend verification, governance, and real UI smoke checks.
- **Placeholder scan:** Every implementation step names exact files, symbols, code, commands, and expected outcomes. No step depends on “TBD”, “TODO”, “similar to”, or an unspecified follow-up.
- **Type consistency:** `dealJourneyProgressColorClass(percent: number): DealJourneyProgressColorClass` is defined in Task 1 and consumed by the exact table/hover helper functions in Tasks 4–5. `indicatorClass?: HTMLAttributes['class']` is defined in Task 2 and passed as `:indicator-class` in Tasks 4–5. The `progress` field key and label are identical in Tasks 3–4.
- **Scope check:** The plan changes one shared utility, one generic component surface, one list field catalog entry, two target renderers, their focused tests, and only the required governance exception. It does not add backend work or modify the board.
- **Dirty-worktree safety:** Each commit stages only task-owned paths; unrelated existing changes remain untouched.
