# Task 5 / Phase 5 Brief: Customer detail opportunity drilldown URL query deep links

Plan source: `/Users/eddie/Code/CRMWolf/docs/superpowers/plans/2026-07-15-customer-opportunity-drilldown.md`

## Context

Phase 1–4 of the customer detail Sheet opportunity drilldown work are already implemented in the working tree. The current goal is Phase 5 only: add URL query deep linking and browser Back behavior for the customer detail Sheet and its embedded opportunity drilldown.

Do not rework Phase 1–4 unless required by this task. Preserve the single-layer Sheet architecture: customer detail Sheet embeds `OpportunityDetailContent.vue` for opportunity detail; do not render `OpportunityDetailSheet.vue` inside `CustomerDetailSheet.vue`.

## Required user-visible URL states

The URL query must be able to represent these UI states:

| UI state | URL |
|---|---|
| Customer list | `/customers` |
| Open customer detail | `/customers?customerId=19` |
| Open customer detail opportunity tab | `/customers?customerId=19&tab=opportunities` |
| Customer detail embedded opportunity detail | `/customers?customerId=19&tab=opportunities&opportunityId=88` |

## Required behavior

1. Synchronize the customer detail Sheet open state to the query.
2. Synchronize the active customer detail tab to the query.
3. Synchronize the embedded opportunity drilldown `opportunityId` to the query.
4. Browser Back behavior must step through:
   - embedded opportunity detail
   - opportunity list tab
   - customer detail Sheet
   - customer list
5. Refreshing/copying a deep link must restore the corresponding state.
6. Entering embedded opportunity drilldown must use `router.push`, not `replace`, so Back can return to the opportunity list.
7. Returning to the opportunity list must remove `opportunityId` from the query.
8. Query and component state must have one clear source of truth. Prefer route query as source of truth for customer detail open state, active tab, and embedded drilldown after this phase.
9. Preserve existing `/opportunities` list page behavior: clicking an opportunity there still opens its own `OpportunityDetailSheet`.
10. Preserve Phase 4 UX: single Sheet, no nested Sheet, clear “返回商机列表”, clear full-detail entry, no double overlay/focus trap.

## Likely files to inspect/change

- `CRM-Client/src/views/Customers.vue`
- `CRM-Client/src/views/CustomerDetailSheet.vue`
- `CRM-Client/tests/views/CustomerDetailSheet.opportunity-drilldown.spec.ts`
- Potentially add a focused URL-query spec near existing customer/opportunity drilldown tests.
- Only touch router/store files if the existing code makes that necessary.

## Testing requirements (TDD)

Follow strict TDD:

1. First add failing tests for Phase 5 behavior.
2. Run the focused test command and confirm the new test fails for the expected missing query behavior.
3. Then implement the minimal production code.
4. Re-run the focused tests and confirm they pass.
5. Run related existing Phase 1–4 tests to prevent regression.
6. Run ESLint/type-check commands appropriate for the modified files if available in package scripts.

Suggested test behaviors:

- Opening a customer detail Sheet from the customers list pushes `customerId` into query.
- Query `customerId` restores an open customer detail Sheet on mount.
- Changing active tab to `opportunities` pushes `tab=opportunities`.
- Query `tab=opportunities` restores the opportunity tab.
- Selecting an opportunity in the customer detail opportunities tab pushes `opportunityId` and keeps `tab=opportunities`.
- Query `customerId=19&tab=opportunities&opportunityId=88` renders embedded `OpportunityDetailContent` with `opportunityId=88`.
- Emitting back from embedded detail removes only `opportunityId`, leaving `customerId` and `tab=opportunities`.
- Closing the customer detail Sheet removes customer-detail query keys.

## Code constraints

From `CRM-Client/CLAUDE.md` and the plan:

- No `any`.
- No `as any`.
- No `@ts-ignore`.
- No non-null assertions.
- Props/emits must be typed.
- New styles, if any, must use `variables-v2.scss` and `$wolf-xxx-v2` tokens. Prefer no new styles for this phase.
- Do not hard-code colors, spacing, radii, or shadows.
- Do not create new permission codes.
- Do not commit changes; leave them in the working tree and report changed files.

## Report contract

Write a full report to:

`/Users/eddie/Code/CRMWolf/docs/superpowers/plans/task-5-phase-5-url-query-report.md`

The report must include:

- Status: `DONE`, `DONE_WITH_CONCERNS`, `NEEDS_CONTEXT`, or `BLOCKED`.
- Files changed.
- Tests added/updated.
- Exact commands run and key output.
- Whether RED was observed before production changes, with the failing command and failure summary.
- Self-review notes.
- Any concerns or blockers.

Return only a short status summary in your final message.