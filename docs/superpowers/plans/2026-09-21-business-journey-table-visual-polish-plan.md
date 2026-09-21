# Business Journey Table Visual Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make business-journey names use the standard blue detail-link treatment and make table stage badges reuse the board's canonical stage colors.

**Architecture:** Extract the existing board stage presentation map into one typed business-journey presentation module. Both the board and table consume that module; the table adds only a `cell-name` link slot and stage badge class binding. No new components, APIs, permissions, routes, or opportunity-create entry.

**Tech Stack:** Vue 3 `<script setup>`, TypeScript, Vitest, Vue Test Utils, Tailwind utility classes, SCSS V2 tokens, CRMWolf DataTable/Badge.

## Global Constraints

- Do not add a 「新建商机」 action or `OpportunityFormDialog` to Business Journeys.
- Preserve DataTable row click, keyboard detail entry, filters, sorts, saved views, table height, and mobile behavior.
- Keep `current_board_stage_label` as the preferred display label; existing fallback labels remain unchanged.
- Stage color class tokens have one source of truth.
- Do not change shared `Badge`, `DataTable`, Button, backend APIs, or schemas.
- Preserve `DS-EX-004` as an exact-token exception; never broaden it to color families.
- Do not touch unrelated dirty `CRM-Server/app/api/opportunities.py` work.

---

### Task 1: Share canonical journey stage presentation

**Files:**
- Create: `CRM-Client/src/components/business-journey/businessJourneyStagePresentation.ts`
- Modify: `CRM-Client/src/components/business-journey/BusinessJourneyBoardView.vue`
- Modify: `CRM-Client/tests/components/BusinessJourneyBoardView.spec.ts`
- Modify: `CRM-Docs/design-system/migration/p2-pkg-04-exceptions.json`

**Interfaces:**
- Produces:

```ts
import type { DealJourneyBoardStage } from '@/schemas/dealJourney'

export interface BusinessJourneyStagePresentation {
  columnClass: string
  badgeClass: string
  emphasisBadgeClass: string
}

export const businessJourneyStagePresentation: Record<
  DealJourneyBoardStage,
  BusinessJourneyStagePresentation
>
```

- `columnClass` keeps the current `business-board-stage--*` classes.
- `badgeClass` keeps the current light background/text/border classes used by board count badges.
- `emphasisBadgeClass` keeps the current solid stage classes used by card emphasis badges.

- [ ] **Step 1: Write failing board palette test**

Extend `BusinessJourneyBoardView.spec.ts` to import the new module and assert all eight stage entries exactly:

```ts
expect(businessJourneyStagePresentation).toEqual({
  early_communication: {
    columnClass: 'business-board-stage--sky',
    badgeClass: 'bg-sky-50 text-sky-700 border-sky-100',
    emphasisBadgeClass: 'bg-sky-600 text-white border-transparent',
  },
  active_progress: {
    columnClass: 'business-board-stage--blue',
    badgeClass: 'bg-blue-50 text-blue-700 border-blue-100',
    emphasisBadgeClass: 'bg-blue-600 text-white border-transparent',
  },
  closing_soon: {
    columnClass: 'business-board-stage--emerald',
    badgeClass: 'bg-emerald-50 text-emerald-700 border-emerald-100',
    emphasisBadgeClass: 'bg-emerald-600 text-white border-transparent',
  },
  contract_processing: {
    columnClass: 'business-board-stage--violet',
    badgeClass: 'bg-violet-50 text-violet-700 border-violet-100',
    emphasisBadgeClass: 'bg-violet-600 text-white border-transparent',
  },
  payment_processing: {
    columnClass: 'business-board-stage--amber',
    badgeClass: 'bg-amber-50 text-amber-700 border-amber-100',
    emphasisBadgeClass: 'bg-amber-600 text-white border-transparent',
  },
  invoice_processing: {
    columnClass: 'business-board-stage--cyan',
    badgeClass: 'bg-cyan-50 text-cyan-700 border-cyan-100',
    emphasisBadgeClass: 'bg-cyan-600 text-white border-transparent',
  },
  completed: {
    columnClass: 'business-board-stage--slate',
    badgeClass: 'bg-slate-50 text-slate-700 border-slate-100',
    emphasisBadgeClass: 'bg-slate-600 text-white border-transparent',
  },
  lost: {
    columnClass: 'business-board-stage--rose',
    badgeClass: 'bg-rose-50 text-rose-700 border-rose-100',
    emphasisBadgeClass: 'bg-rose-600 text-white border-transparent',
  },
})
```

Also retain the existing rendered-column assertion proving `active_progress` still renders `business-board-stage--blue`.

- [ ] **Step 2: Run board test RED**

Run:

```bash
cd CRM-Client && npx vitest run tests/components/BusinessJourneyBoardView.spec.ts
```

Expected: FAIL because `businessJourneyStagePresentation.ts` does not exist.

- [ ] **Step 3: Create shared presentation map**

Create `businessJourneyStagePresentation.ts` with the exact interface and eight entries above. Use literal strings; do not compute Tailwind class names dynamically.

- [ ] **Step 4: Make board consume shared map**

In `BusinessJourneyBoardView.vue`:

```ts
import { businessJourneyStagePresentation } from './businessJourneyStagePresentation'
```

Delete the local `stagePalette`. Replace:

```vue
:class="stagePalette[column.key].column"
:class="stagePalette[column.key].countBadge"
:class="stagePalette[column.key].emphasisBadge"
```

with:

```vue
:class="businessJourneyStagePresentation[column.key].columnClass"
:class="businessJourneyStagePresentation[column.key].badgeClass"
:class="businessJourneyStagePresentation[column.key].emphasisBadgeClass"
```

Do not modify board SCSS or age-tone classes.

- [ ] **Step 5: Move exact-token governance coverage**

Update `DS-EX-004.files` to include:

```json
[
  "CRM-Client/src/components/business-journey/businessJourneyStagePresentation.ts",
  "CRM-Client/src/components/business-journey/BusinessJourneyBoardView.vue",
  "CRM-Client/tests/components/BusinessJourneyBoardView.spec.ts",
  "CRM-Client/tests/components/BusinessJourneyTableView.spec.ts"
]
```

Keep the exact `match` expression unchanged. `BusinessJourneyBoardView.vue` remains because age-tone classes still live there. Do not change `DS-EX-005`.

- [ ] **Step 6: Run focused tests and governance**

Run:

```bash
cd CRM-Client && npx vitest run tests/components/BusinessJourneyBoardView.spec.ts
npm run lint:design-system -- --worktree
```

Expected: board tests pass; design-system governance passes.

- [ ] **Step 7: Commit**

```bash
git add \
  CRM-Client/src/components/business-journey/businessJourneyStagePresentation.ts \
  CRM-Client/src/components/business-journey/BusinessJourneyBoardView.vue \
  CRM-Client/tests/components/BusinessJourneyBoardView.spec.ts \
  CRM-Docs/design-system/migration/p2-pkg-04-exceptions.json
git commit -m "refactor(journey): share stage presentation"
```

---

### Task 2: Add journey name link and colored stage badges

**Files:**
- Modify: `CRM-Client/src/components/business-journey/BusinessJourneyTableView.vue`
- Modify: `CRM-Client/tests/components/BusinessJourneyTableView.spec.ts`

**Interfaces:**
- Consumes: `businessJourneyStagePresentation` from Task 1.
- Existing emit remains:

```ts
'row-click': [payload: { customerId: string; journeyPublicId: string }]
```

- [ ] **Step 1: Write failing table behavior tests**

Extend `BusinessJourneyTableView.spec.ts` with the exact fixture and mount helper below, keeping the existing height test:

```ts
import type { BusinessJourneyListItem } from '@/schemas/dealJourney'

const journeyFixture: BusinessJourneyListItem = {
  id: 'djy_test',
  public_id: 'djy_test',
  name: '华东续约旅程',
  status: 'ACTIVE',
  current_board_stage: 'active_progress',
  current_board_stage_label: '持续推进',
  amount: 168000,
  purchase_type: 'RENEWAL',
  started_at: '2026-09-01T00:00:00',
  closed_at: null,
  last_event_at: '2026-09-20T00:00:00',
  primary_opportunity: null,
  customer_id: 'cus_test',
  customer_name: '示例科技',
  owner: { id: '7', name: '王小明', avatar_url: null },
  primary_opportunity_name: '续约商机',
  product_name: 'CRM 企业版',
  created_time: '2026-09-01T00:00:00',
  expected_closing_date: '2026-10-01',
}

const mountJourneyTable = (data: BusinessJourneyListItem[]) => mount(
  BusinessJourneyTableView,
  {
    props: {
      fields: createBusinessJourneyListFields([]),
      data,
      total: data.length,
      page: 1,
      pageSize: 20,
      filters: [],
      sorts: [],
      columns: [],
      search: '',
      displayMode: 'table',
    },
  },
)
```

Import `createBusinessJourneyListFields` from the existing catalog file. Use this helper in the tests below.

Name-link test:

```ts
it('renders the journey name as the standard detail link and emits one row click', async () => {
  const wrapper = mountJourneyTable([journeyFixture])
  const link = wrapper.get('[data-testid="business-journey-name-link"]')

  expect(link.text()).toBe(journeyFixture.name)
  expect(link.classes()).toContain('business-journey-name-link')

  await link.trigger('click')

  expect(wrapper.emitted('row-click')).toEqual([[
    {
      customerId: journeyFixture.customer_id,
      journeyPublicId: journeyFixture.public_id,
    },
  ]])
})
```

Stage palette table:

```ts
it.each([
  ['early_communication', ['bg-sky-50', 'text-sky-700', 'border-sky-100']],
  ['active_progress', ['bg-blue-50', 'text-blue-700', 'border-blue-100']],
  ['closing_soon', ['bg-emerald-50', 'text-emerald-700', 'border-emerald-100']],
  ['contract_processing', ['bg-violet-50', 'text-violet-700', 'border-violet-100']],
  ['payment_processing', ['bg-amber-50', 'text-amber-700', 'border-amber-100']],
  ['invoice_processing', ['bg-cyan-50', 'text-cyan-700', 'border-cyan-100']],
  ['completed', ['bg-slate-50', 'text-slate-700', 'border-slate-100']],
  ['lost', ['bg-rose-50', 'text-rose-700', 'border-rose-100']],
] as const)('uses the board palette for %s', (stage, classes) => {
  const wrapper = mountJourneyTable([{ ...journeyFixture, current_board_stage: stage }])
  const badge = wrapper.get('[data-testid="business-journey-stage-badge"]')
  expect(badge.classes()).toEqual(expect.arrayContaining([...classes]))
})
```

Keep the existing table-height assertion unchanged.

- [ ] **Step 2: Run table test RED**

Run:

```bash
cd CRM-Client && npx vitest run tests/components/BusinessJourneyTableView.spec.ts
```

Expected: FAIL because the name slot/test IDs and stage classes are absent.

- [ ] **Step 3: Implement name link and stage binding**

In `BusinessJourneyTableView.vue`:

```ts
import { businessJourneyStagePresentation } from './businessJourneyStagePresentation'
```

Add the name slot before the stage slot:

```vue
<template #cell-name="{ row }">
  <span
    class="business-journey-name-link"
    data-testid="business-journey-name-link"
    @click.stop="handleRowClick(row)"
  >
    {{ row.name }}
  </span>
</template>
```

Update the stage Badge:

```vue
<Badge
  variant="outline"
  data-testid="business-journey-stage-badge"
  :class="businessJourneyStagePresentation[row.current_board_stage].badgeClass"
>
  {{ row.current_board_stage_label || stageLabels.get(row.current_board_stage) || '-' }}
</Badge>
```

Add scoped SCSS using existing tokens:

```scss
<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.business-journey-name-link {
  color: $wolf-text-link-v2;
  font-weight: $wolf-font-weight-medium-v2;
  cursor: pointer;

  &:hover {
    color: $wolf-text-link-hover-v2;
  }
}
</style>
```

Do not add a standalone button, route push, or new detail handler.

- [ ] **Step 4: Run table and page tests GREEN**

Run:

```bash
cd CRM-Client && npx vitest run \
  tests/components/BusinessJourneyTableView.spec.ts \
  tests/components/BusinessJourneys.spec.ts \
  tests/components/BusinessJourneyBoardView.spec.ts
```

Expected: all pass.

- [ ] **Step 5: Run governance and production lint**

Run:

```bash
cd CRM-Client
npm run lint:design-system -- --worktree
npx eslint \
  src/components/business-journey/BusinessJourneyTableView.vue \
  src/components/business-journey/BusinessJourneyBoardView.vue \
  src/components/business-journey/businessJourneyStagePresentation.ts \
  --max-warnings=0
```

Expected: pass. Do not lint `tests/components` directly because the repository ESLint project excludes that path; Vitest is its validation seam.

- [ ] **Step 6: Real browser smoke**

At desktop width:

1. Open `/business-journeys` in table mode.
2. Confirm journey names are blue and hover to the existing link-hover blue.
3. Click a journey name and confirm the direct journey Sheet opens once.
4. Verify all eight stage values with seeded/API data or a component showcase: each table Badge uses the same light color family as its board column/count Badge.
5. Switch to board and confirm column backgrounds/count badges/card emphasis colors are unchanged.
6. Return to table and confirm card height remains aligned with Customers/Opportunities.
7. Confirm no 「新建商机」 action appears in the top bar or page toolbar.

- [ ] **Step 7: Commit**

```bash
git add \
  CRM-Client/src/components/business-journey/BusinessJourneyTableView.vue \
  CRM-Client/tests/components/BusinessJourneyTableView.spec.ts
git commit -m "feat(journey): polish table identity and stages"
```

---

## Final Verification

- [ ] Run focused frontend suite:

```bash
cd CRM-Client && npx vitest run \
  tests/components/BusinessJourneyTableView.spec.ts \
  tests/components/BusinessJourneyBoardView.spec.ts \
  tests/components/BusinessJourneys.spec.ts \
  src/components/crmwolf/__tests__/DataTableInteraction.test.ts
```

- [ ] Run design-system governance:

```bash
cd CRM-Client && npm run lint:design-system -- --worktree
```

- [ ] Confirm only intended files changed and unrelated `CRM-Server/app/api/opportunities.py` remains untouched:

```bash
git status --short
git diff --check
```

- [ ] Review the two commits against `docs/superpowers/specs/2026-09-21-business-journey-table-visual-polish-design.md`.
