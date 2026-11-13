# CRM-111 Button Interaction Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply the approved button-boundary rules to confirmed CRM-111 deviations without replacing complex native controls or touching CRM-110/CRM-113 implementation ownership.

**Architecture:** Keep native buttons for disclosure, selection cards, chart buckets, detail rows, and panel back events. Migrate only clearly ordinary action controls to the existing `ui/button` where the surrounding layout permits it; change stable mobile navigation to links while retaining the current active-state and touch contract. Repair target-size and semantic gaps in small icon/tooltip controls, and use native buttons for BoardView cards only if the slot action boundary cannot remain separate.

**Tech Stack:** Vue 3, TypeScript, vue-router, reka-ui primitives, shadcn-vue `Button`, Vitest, Playwright, Vite.

## Global Constraints

- Do not modify `AgentUIInteractionBlock.vue` implementation owned by CRM-110.
- Do not modify the four entity chart page implementations owned by CRM-113; record their contract only.
- Preserve form submission, chart drill-down, disclosure, selection, navigation, panel-back, and focus-restoration behavior.
- Ordinary submit/save/confirm/delete/retry actions prefer `CRM-Client/src/components/ui/button/Button.vue`.
- Stable URL navigation uses links; panel-state back/close remains a button.
- Every interactive control retains a readable accessible name, visible focus, correct disabled/loading semantics, and a minimum 44px effective touch target on narrow viewports.
- Avoid nested interactive elements.
- No product-code change is accepted without a behavior test or an actual runtime smoke check covering the changed contract.
- Private workflow artifacts remain under `.xwing-task/crmwolf/` and are not committed.

## File map

- `CRM-Client/src/components/crmwolf/BottomNavItem.vue`: render stable route navigation as a link while preserving active state, label, focus, and touch sizing.
- `CRM-Client/src/components/crmwolf/BottomNav.vue`: pass route target to `BottomNavItem`; remove redundant click-router bridge only if the child owns navigation.
- `CRM-Client/src/components/FollowUpList.vue`: make the HoverInfo effectiveness trigger a real 44px control without changing its informational behavior.
- `CRM-Client/src/components/crmwolf/ListViewStateSummary.vue`: make removable-filter control target 44px without changing chip density.
- `CRM-Client/src/components/ApprovalSourceHeader.vue`: add missing accessible name and make the panel-back controls 44px effective targets while preserving emitted back event.
- `CRM-Client/src/components/crmwolf/TouchInput.vue`: propagate disabled state to password visibility toggle; preserve aria-pressed and label.
- `CRM-Client/src/components/crmwolf/BoardView.vue`: use a native button for the card surface only if the actions slot remains outside the button; otherwise retain current role-button and verify its keyboard contract.
- `CRM-Client/src/components/crmwolf/__tests__/BoardView.test.ts`: protect card keyboard activation, action isolation, and view-all disabled behavior.
- `CRM-Client/src/components/crmwolf/__tests__/BottomNavItem.test.ts`: protect link semantics and active state.
- `CRM-Client/src/components/crmwolf/__tests__/TouchInput.test.ts`: protect disabled password toggle semantics.
- `CRM-Client/src/components/crmwolf/__tests__/AccessibilityFeedback.test.ts`: protect accessible names and focus behavior where existing shared coverage fits.
- `docs/superpowers/plans/2026-11-13-crm-111-button-contract.md`: durable implementation plan.

## Task 1: Convert stable bottom navigation to links

**Files:**
- Modify: `CRM-Client/src/components/crmwolf/BottomNavItem.vue`
- Modify: `CRM-Client/src/components/crmwolf/BottomNav.vue`
- Create: `CRM-Client/src/components/crmwolf/__tests__/BottomNavItem.test.ts`

**Interfaces:**
- `BottomNavItem` consumes `{ item: { route, icon, label }, active }` and emits no navigation event after the cutover.
- The rendered route item produces a router-aware link with `aria-current="page"` only when active.

- [ ] Write a failing test mounting `BottomNavItem` with a router link and assert the rendered element is an anchor with the expected route, accessible label, and active `aria-current`.
- [ ] Run `npm run test:unit -- src/components/crmwolf/__tests__/BottomNavItem.test.ts`; expect failure because the current component renders `button`.
- [ ] Implement the smallest link cutover: use the project’s existing `RouterLink`/router-link pattern, preserve `itemClasses`, icon, label, `min-w-touch-target min-h-touch-target`, and focus-visible styling; remove the manual Enter/Space handler because links provide native keyboard activation.
- [ ] Update `BottomNav.vue` so it passes the route target and no longer routes the child click event.
- [ ] Run the focused test and the existing navigation tests; expect pass.

## Task 2: Repair small informational and icon control contracts

**Files:**
- Modify: `CRM-Client/src/components/FollowUpList.vue`
- Modify: `CRM-Client/src/components/crmwolf/ListViewStateSummary.vue`
- Modify: `CRM-Client/src/components/ApprovalSourceHeader.vue`
- Modify: `CRM-Client/src/components/crmwolf/TouchInput.vue`
- Modify: `CRM-Client/src/components/crmwolf/__tests__/AccessibilityFeedback.test.ts`
- Create or modify: `CRM-Client/src/components/crmwolf/__tests__/TouchInput.test.ts`

**Interfaces:**
- Effectiveness HoverInfo remains informational and click does not start a new business action.
- Approval source back controls continue emitting `back` and remain panel-state buttons.
- Password visibility toggle remains a button with state-dependent `aria-label` and `aria-pressed`.

- [ ] Write failing component tests for the disabled password toggle and approval breadcrumb accessible name.
- [ ] Run the focused tests and confirm the failures reflect missing disabled/name behavior.
- [ ] Set the effectiveness trigger, removable-filter button, and approval header controls to an effective 44px target using existing touch-target utilities or wrapper geometry; do not change visual information density beyond the approved Q2 click-box decision.
- [ ] Add `aria-label="返回审批详情"` to the approval breadcrumb button.
- [ ] Bind `:disabled="disabled"` to the password toggle and expose the disabled visual/pointer semantics consistent with the component’s input state.
- [ ] Run focused tests and existing accessibility tests.

## Task 3: Resolve BoardView card semantics without nested interaction

**Files:**
- Modify: `CRM-Client/src/components/crmwolf/BoardView.vue`
- Modify: `CRM-Client/src/components/crmwolf/__tests__/BoardView.test.ts`

**Interfaces:**
- Card activation remains `activateCard(column, card)` for click, Enter, and Space.
- `card-actions` slot controls remain independently operable and never trigger card activation.
- `viewAll(column)` remains disabled when `columnDrillEnabled(column)` is false.

- [ ] Write or extend failing tests proving keyboard card activation and action-slot isolation from the public rendered behavior.
- [ ] Run the focused tests and confirm the current role-button implementation fails only where the approved contract requires native semantics or action isolation.
- [ ] Implement the smallest safe structure: prefer a native `button` card surface only when action-slot content can be rendered as a sibling; otherwise retain `article[role="button"]`, keep explicit Enter/Space handling, and add the missing disabled/focus contract without placing nested controls inside a button.
- [ ] Run `BoardView.test.ts` and type-check.

## Task 4: Migrate ordinary action controls that are not owned by CRM-110/113

**Files:**
- Modify only ordinary-action sites identified after Tasks 1–3: `CRM-Client/src/components/sales-assistant/SalesAssistantChat.vue`, `CRM-Client/src/components/crmwolf/FormErrorSummary.vue`, `CRM-Client/src/components/crmwolf/BoardView.vue`, and any ordinary-action “查看更多” control outside CRM-113-owned chart pages.
- Add or update the nearest existing behavior tests.

**Interfaces:**
- Existing click handlers and disabled/loading conditions remain unchanged.
- `ui/button` is used only where its primitive composition does not create nested interactive elements or lose text-button layout.

- [ ] Add behavior assertions for one ordinary action per site before changing markup.
- [ ] Run the focused tests to establish the red state for the new component contract where applicable.
- [ ] Replace only eligible ordinary-action controls with `ui/button`, preserving `variant`, compact layout class, readable text, and disabled/loading state.
- [ ] Leave chart-page ordinary actions and AgentUIInteractionBlock implementation untouched; record them as cross-task references.
- [ ] Run focused tests, lint, and type-check.

## Task 5: Verify the complete interaction contract

**Files:**
- Modify: `.xwing-task/crmwolf/state.json` only for private evidence.
- Create: `.xwing-task/crmwolf/findings.md` and `.xwing-task/crmwolf/verification.md`.

- [ ] Run unit tests covering changed components.
- [ ] Run `npm run type-check`, `npm run lint`, `npm run lint:design-system`, and `npm run test:governance`.
- [ ] Start the actual Vite surface and use Playwright at mobile and desktop widths to verify tab order, Enter/Space behavior, focus-visible, disabled/loading state, nested interaction isolation, and effective target sizes.
- [ ] Record exact commands, observed results, remaining CRM-110/CRM-113 references, and any blocker in the private verification artifact.
- [ ] Update the task ledger only after evidence is captured.

## Self-review checklist

- Every CRM-108 item has a conclusion in `idea.md`.
- No change touches CRM-110 or CRM-113-owned implementation files.
- No stable route remains a button where a link is expressible; panel back remains a button.
- No nested button/link is introduced.
- No assertion pins incidental class strings when behavior can be asserted through role, name, state, or event outcome.
- Verification claims match commands actually run.
