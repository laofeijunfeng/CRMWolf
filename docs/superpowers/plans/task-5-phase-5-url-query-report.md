# Task 5 / Phase 5 URL query report

## Status

DONE_WITH_CONCERNS

Phase 5 URL query deep links and browser Back stepping behavior were implemented for the customer detail Sheet and embedded opportunity drilldown.

Implemented behavior:

- `/customers` remains the customer list state.
- `/customers?customerId=19` opens the customer detail Sheet.
- `/customers?customerId=19&tab=opportunities` restores the customer detail opportunities tab.
- `/customers?customerId=19&tab=opportunities&opportunityId=88` restores the embedded opportunity detail content inside the existing customer Sheet.
- Opening a customer detail from the list uses `router.push` to add `customerId`.
- Switching customer detail tabs uses `router.push` to update/remove `tab`.
- Selecting an embedded opportunity uses `router.push` to add `opportunityId` and keep `tab=opportunities`.
- Returning from embedded opportunity detail removes only `opportunityId`, leaving `customerId` and `tab=opportunities`.
- Closing the customer detail Sheet removes `customerId`, `tab`, and `opportunityId` while preserving unrelated query keys.
- Existing single-layer Sheet architecture is preserved; `CustomerDetailSheet.vue` still renders `OpportunityDetailContent.vue`, not `OpportunityDetailSheet.vue`.

## Files changed

Task-specific files changed:

- `/Users/eddie/Code/CRMWolf/CRM-Client/src/views/Customers.vue`
- `/Users/eddie/Code/CRMWolf/CRM-Client/src/views/CustomerDetailSheet.vue`
- `/Users/eddie/Code/CRMWolf/CRM-Client/tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts`
- `/Users/eddie/Code/CRMWolf/CRM-Client/tests/views/Customers.url-query.spec.ts`
- `/Users/eddie/Code/CRMWolf/docs/superpowers/plans/task-5-phase-5-url-query-report.md`

Observed pre-existing modified file still present in focused status but not retained as a task-specific change:

- `/Users/eddie/Code/CRMWolf/CRM-Client/src/api/customer.ts` was already modified in the working tree before this task; I briefly tried adding a local type there, then reverted that addition and used a local row type in `Customers.vue` instead.

## Tests added/updated

- Updated `/Users/eddie/Code/CRMWolf/CRM-Client/tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts` with Phase 5 query coverage:
  - restores opportunities tab from route query on mount
  - pushes `tab=opportunities` when switching tabs
  - pushes `opportunityId` and keeps `tab=opportunities` when selecting embedded opportunity
  - restores embedded `OpportunityDetailContent` from deep link
  - removes only `opportunityId` when returning to the opportunities list
- Added `/Users/eddie/Code/CRMWolf/CRM-Client/tests/views/Customers.url-query.spec.ts` covering:
  - opening customer detail from the list pushes `customerId`
  - `customerId` query restores open customer detail Sheet on mount
  - closing customer detail removes customer-detail query keys while preserving unrelated query keys

## Exact commands run and key output

### Worktree / setup checks

```bash
GIT_DIR=$(cd "$(git rev-parse --git-dir)" 2>/dev/null && pwd -P) && GIT_COMMON=$(cd "$(git rev-parse --git-common-dir)" 2>/dev/null && pwd -P) && BRANCH=$(git branch --show-current) && SUPER=$(git rev-parse --show-superproject-working-tree 2>/dev/null || true) && printf 'GIT_DIR=%s
GIT_COMMON=%s
BRANCH=%s
SUPER=%s
PWD=%s
' "$GIT_DIR" "$GIT_COMMON" "$BRANCH" "$SUPER" "$PWD"
```

Key output:

```text
GIT_DIR=/Users/eddie/Code/CRMWolf/.git/worktrees/agent-a8f68be0e937928c2
GIT_COMMON=/Users/eddie/Code/CRMWolf/.git
BRANCH=worktree-agent-a8f68be0e937928c2
SUPER=
PWD=/Users/eddie/Code/CRMWolf/.claude/worktrees/agent-a8f68be0e937928c2
```

I then implemented in `/Users/eddie/Code/CRMWolf` per task instruction to work in the existing checkout.

### RED: focused CustomerDetailSheet query tests before production code

```bash
npm --prefix /Users/eddie/Code/CRMWolf/CRM-Client run test:unit -- tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts
```

Key output:

```text
❯ tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts (8 tests | 5 failed)
× restores the opportunities tab from the route query on mount
  → expected 'false' to be 'true'
× pushes the active tab into the route query when switching to opportunities
  → expected last "spy" call to have been called with [ { path: '/customers', query: { customerId: '19', tab: 'opportunities' } } ]
× pushes opportunityId and keeps the opportunities tab when selecting an embedded opportunity
  → Unable to get [data-testid="view-opportunity"] ... active tab remained followup
```

### RED: focused Customers query tests before production code

```bash
npm --prefix /Users/eddie/Code/CRMWolf/CRM-Client run test:unit -- tests/views/Customers.url-query.spec.ts
```

Key output:

```text
❯ tests/views/Customers.url-query.spec.ts (3 tests | 3 failed)
× pushes customerId into the route query when opening a customer detail sheet from the list
  → Received: undefined
× restores an open customer detail sheet from customerId in the route query on mount
  → expected 'false' to be 'true'
× removes customer detail query keys when closing the customer detail sheet
  → Received: undefined
```

### GREEN: focused Phase 5 tests after production code

```bash
npm --prefix /Users/eddie/Code/CRMWolf/CRM-Client run test:unit -- tests/views/Customers.url-query.spec.ts tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts
```

Key output:

```text
✓ tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts (8 tests)
✓ tests/views/Customers.url-query.spec.ts (3 tests)
Test Files  2 passed (2)
Tests  11 passed (11)
```

### Related Phase 1–4 regression tests

```bash
npm --prefix /Users/eddie/Code/CRMWolf/CRM-Client run test:unit -- tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts tests/views/Customers.url-query.spec.ts tests/views/OpportunityDetailSheet.content-reuse.spec.ts tests/components/OpportunitiesPanel.drilldown.spec.ts tests/components/OpportunitiesPanel.experience.spec.ts tests/components/OpportunityDetailContent.experience.spec.ts
```

Final key output:

```text
✓ tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts (8 tests)
✓ tests/views/Customers.url-query.spec.ts (3 tests)
✓ tests/components/OpportunityDetailContent.experience.spec.ts (3 tests)
✓ tests/views/OpportunityDetailSheet.content-reuse.spec.ts (1 test)
✓ tests/components/OpportunitiesPanel.drilldown.spec.ts (2 tests)
✓ tests/components/OpportunitiesPanel.experience.spec.ts (2 tests)
Test Files  6 passed (6)
Tests  19 passed (19)
```

### Targeted ESLint

First attempts:

```bash
npm --prefix /Users/eddie/Code/CRMWolf/CRM-Client exec eslint -- src/views/Customers.vue src/views/CustomerDetailSheet.vue
```

Key output:

```text
No files matching the pattern "src/views/Customers.vue" were found.
```

```bash
npm --prefix /Users/eddie/Code/CRMWolf/CRM-Client exec eslint -- /Users/eddie/Code/CRMWolf/CRM-Client/src/views/Customers.vue /Users/eddie/Code/CRMWolf/CRM-Client/src/views/CustomerDetailSheet.vue
```

Key output:

```text
ESLint couldn't find an eslint.config.(js|mjs|cjs) file.
```

Correct command:

```bash
cd /Users/eddie/Code/CRMWolf/CRM-Client && npm exec eslint -- src/views/Customers.vue src/views/CustomerDetailSheet.vue
```

Initial key output found existing `Customers.vue` strict TypeScript rule violations, including `as any` / `any` in the modified file. I fixed those while keeping the task focused.

Final key output:

```text
# no output; exit code 0
```

### Type-check

```bash
npm --prefix /Users/eddie/Code/CRMWolf/CRM-Client run type-check
```

Key output: failed due to many existing unrelated project errors, starting with:

```text
src/api/aiConfig.ts(45,24): error TS2558: Expected 0-1 type arguments, but got 2.
src/api/aiConfig.ts(52,25): error TS2558: Expected 0-1 type arguments, but got 2.
src/api/contract.ts(133,6): error TS6196: 'ApiResponse' is declared but never used.
src/api/example-customer.ts(15,8): error TS2305: Module '"@/schemas/customer"' has no exported member 'PaginatedResponse'.
src/api/example-customer.ts(73,27): error TS2552: Cannot find name 'CustomerCreateSchema'. Did you mean 'CustomerResponseSchema'?
...
```

I then checked that modified files are not among the current type-check failures:

```bash
npm --prefix /Users/eddie/Code/CRMWolf/CRM-Client run type-check -- --pretty false 2>&1 | rg "src/(views/Customers\.vue|views/CustomerDetailSheet\.vue|api/customer\.ts|tests/views/Customers\.url-query\.spec\.ts|tests/views/CustomerDetailSheet\.opportunity-drilldown\.spec\.ts)" || true
```

Final key output:

```text
# no output; modified files are not in type-check errors
```

## RED observed details

RED was observed before production changes for both new/updated focused specs:

1. `CustomerDetailSheet.opportunity-drilldown.spec.ts`: 5 expected failures for missing query source-of-truth behavior.
2. `Customers.url-query.spec.ts`: 3 expected failures for missing customer detail Sheet query synchronization.

The failures were expected feature-missing failures, not syntax/setup failures.

## Self-review notes

- Route query is now the source of truth for customer detail open state in `Customers.vue`; `selectedCustomerId` and `sheetVisible` derive from `customerId`.
- `CustomerDetailSheet.vue` derives initial active tab and embedded opportunity drilldown from the route query on mount and watches query changes so browser Back/Forward can step through query states.
- Entering the embedded opportunity drilldown uses `router.push`, satisfying Back behavior requirements.
- Returning from embedded detail uses `router.push` to remove only `opportunityId` and preserve `customerId` + `tab=opportunities`.
- Closing customer detail removes only customer-detail query keys and preserves unrelated query keys.
- Existing `/opportunities` page behavior was not changed; no `OpportunityDetailSheet.vue` rendering was introduced inside `CustomerDetailSheet.vue`.
- No new styles were added.
- I avoided introducing `any`, `as any`, `@ts-ignore`, or non-null assertions in the task changes. I also removed existing `any` / `as any` violations from touched portions of `Customers.vue` so targeted ESLint can pass.

## Concerns / blockers

- `npm run type-check` still fails because of many pre-existing unrelated project-wide TypeScript errors. The modified Phase 5 files are not present in the filtered type-check output.
- The working tree had many pre-existing uncommitted changes and untracked files before this task. I did not commit and did not attempt to clean unrelated changes.
- Test output includes repeated Sass legacy JS API deprecation warnings from the existing toolchain; tests still pass.


---

## Review findings fix pass: embedded back history + visible customerId reload

### Fix status

DONE_WITH_CONCERNS

Fixed the two Important review findings:

1. `CustomerDetailSheet.vue` now uses `router.replace` for the UI “返回商机列表” action, removing only `opportunityId` while preserving `customerId` and `tab=opportunities`. Entering embedded opportunity drilldown still uses `router.push`.
2. `CustomerDetailSheet.vue` now watches `customerId` while the Sheet is visible and reloads all customer detail data when the id changes. It does not reload when the Sheet is closed or when the new id is `null`.

### Files changed

- `/Users/eddie/Code/CRMWolf/CRM-Client/src/views/CustomerDetailSheet.vue`
- `/Users/eddie/Code/CRMWolf/CRM-Client/tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts`
- `/Users/eddie/Code/CRMWolf/docs/superpowers/plans/task-5-phase-5-url-query-report.md`

### Tests added/updated for the two findings

- Updated `/Users/eddie/Code/CRMWolf/CRM-Client/tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts` so returning from embedded opportunity detail asserts `router.replace` is used with `{ customerId: '19', tab: 'opportunities' }`, and `router.push` is not used for that UI back action.
- Added a focused test in the same spec asserting that changing `customerId` from `19` to `42` while `visible=true` reloads every customer detail data source with id `42`.

### Exact commands run and key output

```bash
python3 - <<'PY'
# edited CustomerDetailSheet.opportunity-drilldown.spec.ts to add RED tests
PY
```

Key output: no output; file edit completed.

```bash
npm --prefix /Users/eddie/Code/CRMWolf/CRM-Client run test:unit -- tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts
```

RED key output:

```text
❯ tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts (9 tests | 2 failed) 612ms
× CustomerDetailSheet opportunity drilldown > reloads all customer detail data when customerId changes while visible
  → expected "spy" to be called with arguments: [ 42 ]
  Number of calls: 0
× CustomerDetailSheet opportunity drilldown > replaces only opportunityId in the route query when returning to the opportunities list
  → expected last "spy" call to have been called with [ { path: '/customers', …(1) } ]
```

```bash
python3 - <<'PY'
# edited CustomerDetailSheet.vue to add replace navigation helper and visible customerId watcher
PY
```

Key output: no output; file edit completed.

```bash
npm --prefix /Users/eddie/Code/CRMWolf/CRM-Client run test:unit -- tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts
```

GREEN key output:

```text
✓ tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts (9 tests) 361ms
Test Files  1 passed (1)
Tests  9 passed (9)
```

```bash
npm --prefix /Users/eddie/Code/CRMWolf/CRM-Client run test:unit -- tests/views/Customers.url-query.spec.ts tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts tests/views/OpportunityDetailSheet.content-reuse.spec.ts tests/components/OpportunitiesPanel.drilldown.spec.ts tests/components/OpportunitiesPanel.experience.spec.ts tests/components/OpportunityDetailContent.experience.spec.ts
```

Key output:

```text
✓ tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts (9 tests) 330ms
✓ tests/views/Customers.url-query.spec.ts (3 tests) 51ms
✓ tests/components/OpportunityDetailContent.experience.spec.ts (3 tests) 90ms
✓ tests/views/OpportunityDetailSheet.content-reuse.spec.ts (1 test) 32ms
✓ tests/components/OpportunitiesPanel.drilldown.spec.ts (2 tests) 17ms
✓ tests/components/OpportunitiesPanel.experience.spec.ts (2 tests) 11ms
Test Files  6 passed (6)
Tests  20 passed (20)
```

```bash
cd /Users/eddie/Code/CRMWolf/CRM-Client && npm exec eslint -- src/views/CustomerDetailSheet.vue tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts
```

Key output:

```text
/Users/eddie/Code/CRMWolf/CRM-Client/tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts
  0:0  error  Parsing error: "parserOptions.project" has been provided for @typescript-eslint/parser.
The file was not found in any of the provided project(s): tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts
```

```bash
cd /Users/eddie/Code/CRMWolf/CRM-Client && npm exec eslint -- src/views/CustomerDetailSheet.vue
```

Key output: no output; exit code 0.

```bash
npm --prefix /Users/eddie/Code/CRMWolf/CRM-Client run type-check
```

Key output: failed due to existing unrelated project-wide TypeScript errors, starting with:

```text
src/api/aiConfig.ts(45,24): error TS2558: Expected 0-1 type arguments, but got 2.
src/api/aiConfig.ts(52,25): error TS2558: Expected 0-1 type arguments, but got 2.
src/api/contract.ts(133,6): error TS6196: 'ApiResponse' is declared but never used.
src/api/example-customer.ts(15,8): error TS2305: Module '"@/schemas/customer"' has no exported member 'PaginatedResponse'.
src/api/example-customer.ts(73,27): error TS2552: Cannot find name 'CustomerCreateSchema'. Did you mean 'CustomerResponseSchema'?
```

```bash
npm --prefix /Users/eddie/Code/CRMWolf/CRM-Client run type-check -- --pretty false 2>&1 | rg "src/views/CustomerDetailSheet\.vue|tests/views/CustomerDetailSheet\.opportunity-drilldown\.spec\.ts" || true
```

Key output: no output; modified files were not present in type-check errors.

```bash
rg "as any|@ts-ignore|\bany\b|![).;\],}]|!:" /Users/eddie/Code/CRMWolf/CRM-Client/src/views/CustomerDetailSheet.vue /Users/eddie/Code/CRMWolf/CRM-Client/tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts || true
```

Key output: no output; no forbidden TypeScript patterns found in the modified files.

### RED observed details for the new/updated fix tests

RED was observed before production changes:

- The new visible `customerId` change test failed because no reload happened after `customerId` changed to `42` while the Sheet stayed visible.
- The updated embedded-detail back test failed because `router.replace` was never called; the existing behavior still used the push-only query helper.

### Self-review notes

- The UI back action from embedded opportunity detail now uses `replaceCustomerDetailQuery('opportunities')`, so it removes only `opportunityId` without creating a browser-history entry that would reopen the just-dismissed detail on Back.
- `handleViewOpportunity` still calls `pushCustomerDetailQuery('opportunities', opportunityId)`, preserving the intended Back step from detail to the opportunity list.
- The `customerId` watcher guards against closed/null/no-op states and reloads through the existing `loadAllData` path so customer, score, follow-ups, opportunities, contracts, invoice titles, license applications, and deployments are refreshed consistently.
- The single-layer Sheet architecture remains unchanged; `CustomerDetailSheet.vue` continues to embed `OpportunityDetailContent.vue` directly.
- No new styles were added for this fix pass.

### Concerns / blockers

- Project-wide `npm run type-check` still fails due to pre-existing unrelated TypeScript errors. The filtered type-check output showed no errors in the modified files.
- ESLint cannot parse the focused spec through the current project configuration because the test file is outside the configured `parserOptions.project`; targeted ESLint on the modified source file passed.
- Test output continues to include existing Dart Sass legacy JS API deprecation warnings.

---

## Review finding fix pass: stale customer detail load responses

### Fix status

DONE_WITH_CONCERNS

Fixed the remaining Phase 5 review finding in `CustomerDetailSheet.vue`: overlapping `loadAllData` calls now use a monotonically increasing request id so only the latest request can assign customer detail UI state, handle load errors, or clear `loading`. Older completions return without updating `customer`, `score`, `followUps`, `opportunities`, `contracts`, `invoiceTitles`, `licenseApplications`, or `deployments`.

### Files changed

- `/Users/eddie/Code/CRMWolf/CRM-Client/src/views/CustomerDetailSheet.vue`
- `/Users/eddie/Code/CRMWolf/CRM-Client/tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts`
- `/Users/eddie/Code/CRMWolf/docs/superpowers/plans/task-5-phase-5-url-query-report.md`

### Test added / updated

- Added a focused regression test in `/Users/eddie/Code/CRMWolf/CRM-Client/tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts` that starts visible customer `19`, changes props/query to customer `42`, resolves the `42` customer-detail promise first, then resolves stale `19`, and asserts the mocked embedded `OpportunityDetailContent` customer context still renders customer `42` / `客户 42`.
- Updated the `OpportunityDetailContent` test mock to expose `customerContext.customerId` and `customerContext.customerName` as DOM attributes for an observable data-driven assertion.

### Exact commands run and key output

```bash
npm --prefix /Users/eddie/Code/CRMWolf/CRM-Client run test:unit -- tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts
```

RED key output:

```text
❯ tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts (10 tests | 1 failed) 105ms
× CustomerDetailSheet opportunity drilldown > keeps the latest customer detail data when an older load resolves after a customerId change
  → expected '客户 19' to be '客户 42' // Object.is equality
Test Files  1 failed (1)
Tests  1 failed | 9 passed (10)
```

```bash
npm --prefix /Users/eddie/Code/CRMWolf/CRM-Client run test:unit -- tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts
```

GREEN key output:

```text
✓ tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts (10 tests) 128ms
Test Files  1 passed (1)
Tests  10 passed (10)
```

```bash
npm --prefix /Users/eddie/Code/CRMWolf/CRM-Client run test:unit -- tests/views/Customers.url-query.spec.ts tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts tests/views/OpportunityDetailSheet.content-reuse.spec.ts tests/components/OpportunitiesPanel.drilldown.spec.ts tests/components/OpportunitiesPanel.experience.spec.ts tests/components/OpportunityDetailContent.experience.spec.ts
```

Related Phase 5 regression key output:

```text
✓ tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts (10 tests) 104ms
✓ tests/views/Customers.url-query.spec.ts (3 tests) 16ms
✓ tests/components/OpportunityDetailContent.experience.spec.ts (3 tests) 56ms
✓ tests/views/OpportunityDetailSheet.content-reuse.spec.ts (1 test) 7ms
✓ tests/components/OpportunitiesPanel.drilldown.spec.ts (2 tests) 14ms
✓ tests/components/OpportunitiesPanel.experience.spec.ts (2 tests) 19ms
Test Files  6 passed (6)
Tests  21 passed (21)
```

```bash
cd /Users/eddie/Code/CRMWolf/CRM-Client && npm exec eslint -- src/views/CustomerDetailSheet.vue
```

Key output: no output; exit code 0.

```bash
cd /Users/eddie/Code/CRMWolf/CRM-Client && npm exec eslint -- tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts
```

Known test parser limitation output:

```text
/Users/eddie/Code/CRMWolf/CRM-Client/tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts
  0:0  error  Parsing error: "parserOptions.project" has been provided for @typescript-eslint/parser.
The file was not found in any of the provided project(s): tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts
```

```bash
rg "as any|@ts-ignore|\bany\b|![).;\],}]|!:" /Users/eddie/Code/CRMWolf/CRM-Client/src/views/CustomerDetailSheet.vue /Users/eddie/Code/CRMWolf/CRM-Client/tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts || true
```

Key output: no output; no forbidden TypeScript patterns found in the modified files.

### RED observed details

The new stale-load test failed before the production guard because resolving customer `19` after customer `42` overwrote the embedded opportunity detail customer context name from `客户 42` back to stale `客户 19`. This was the expected feature-missing failure, not a syntax or setup error.

### Self-review notes

- The fix is intentionally minimal: `loadAllData` snapshots a request id at start and compares it before assigning data, before calling `handleApiError`, and before clearing `loading`.
- Latest valid loads keep existing behavior, including the existing per-resource fallback catches and top-level customer-detail error handling.
- Stale load completions do not assign any UI state and do not clear loading for a newer request.
- Existing Phase 5 URL behavior is preserved: entering embedded opportunity drilldown still uses `router.push`, UI back still uses `router.replace`, and visible `customerId` changes still trigger reload.
- No `any`, `as any`, `@ts-ignore`, or non-null assertions were introduced.

### Concerns / blockers

- Targeted ESLint passes for `/Users/eddie/Code/CRMWolf/CRM-Client/src/views/CustomerDetailSheet.vue`, but the current ESLint project configuration cannot parse `/Users/eddie/Code/CRMWolf/CRM-Client/tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts` because that test file is outside the configured `parserOptions.project`.
- Test runs continue to emit existing Dart Sass legacy JS API deprecation warnings from the toolchain; all focused and related tests still pass.
- The repository already had a large uncommitted working tree before this fix; I only touched the requested files for this pass and did not commit.
