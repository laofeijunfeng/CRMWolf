# 客户创建弹窗联系人顺序与折叠过渡实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 创建弹窗把联系人放在「更多客户信息」之上，并为更多信息补上与 Accordion 同节奏的高度展开/收起过渡。

**Architecture:** 继续用现有 shadcn-vue / Reka `Collapsible`。只调整 `CustomerFormDialog` 的区块 DOM 顺序；在 `tailwind.config.ts` 补上缺失的 `collapsible-down/up` keyframes（高度变量 `--reka-collapsible-content-height`）；把折叠区 layout class 挪到 `CollapsibleContent` 内层，并在该弹窗关闭卸载（`unmount-on-hide="false"`），让收起动画有内容可播。

**Tech Stack:** Vue 3 + TypeScript + Vitest + Tailwind + Reka UI Collapsible。

## Global Constraints

- 业务合同仍是 `docs/superpowers/specs/2026-09-11-customer-edit-progressive-disclosure-design.md`；本计划只覆盖 `docs/superpowers/specs/2026-09-15-customer-create-contact-order-collapsible-motion-design.md`。
- 不改保存契约、字段、权限、License 边界。
- 不把联系人放进「更多客户信息」。
- 不新增组件，不把这段改成 Accordion，不手写第二套 height 动画。
- 不改编辑模式结构（编辑没有联系人区块）。
- 不把这次修复扩到其他 Collapsible 调用方的 markup。
- 不为 keyframes 写快照测试。
- 前端禁止 `any`、`as any`、`@ts-ignore` 和无必要的非空断言。
- 不重置、覆盖或提交与本功能无关的 dirty/staged 文件。
- 中间任务只跑聚焦测试；不要跑全量 lint / type-check / 浏览器 smoke，除非本任务步骤写明。

---

## Task 1: Put create-mode contacts above more-information

**Files:**
- Modify: `CRM-Client/src/components/dialogs/__tests__/CustomerFormDialog.test.ts`
- Modify: `CRM-Client/src/components/dialogs/CustomerFormDialog.vue:780-910`
- Modify: `docs/superpowers/specs/2026-09-15-customer-create-contact-order-collapsible-motion-design.md` 状态行改为已确认

**Interfaces:**

- Consumes: 现有 `mountCreate()` / `mountEdit()` 与 `#customer-contact-name`、`#customer-more-info-trigger`。
- Produces: 创建模式 DOM 顺序为「基础信息 → 联系人信息 → 更多客户信息 → Footer」；编辑模式仍无联系人区块。

### Step 1: Write failing order tests

In `CRM-Client/src/components/dialogs/__tests__/CustomerFormDialog.test.ts`, immediately after `renders the more-information trigger collapsed in create and edit modes`, add:

```typescript
it('places create contact fields above the more-information trigger', async () => {
  vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
  vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
  const wrapper = mountCreate()
  await flushPromises()
  const contact = wrapper.get('#customer-contact-name').element
  const trigger = wrapper.get('#customer-more-info-trigger').element
  expect(contact.compareDocumentPosition(trigger) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(wrapper.get('#customer-contact-name').exists()).toBe(true)
  wrapper.unmount()
})

it('does not render contact fields in edit mode', async () => {
  vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
  vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
  const wrapper = mountEdit()
  await flushPromises()
  expect(wrapper.find('#customer-contact-name').exists()).toBe(false)
  expect(wrapper.find('#customer-more-info-trigger').exists()).toBe(true)
  wrapper.unmount()
})
```

Do not change `mountCreate` / `mountEdit`.

### Step 2: Run the new tests and watch the order case fail

Run:

```bash
cd CRM-Client && npm run test:unit -- --run src/components/dialogs/__tests__/CustomerFormDialog.test.ts
```

Expected: `places create contact fields above the more-information trigger` fails because `#customer-contact-name` currently follows `#customer-more-info-trigger`. The edit-mode absence test should already pass.

### Step 3: Reorder the create-mode markup

In `CRM-Client/src/components/dialogs/CustomerFormDialog.vue`, move the entire create-only contact block that currently starts at:

```vue
<div v-if="mode === 'create'" class="space-y-4 pt-4 border-t">
  <h3 class="text-sm font-medium text-muted-foreground">联系人信息</h3>
```

so it sits **after** the basic-info `</div>` (the block that ends with the address `FormField`) and **before** `<Collapsible`.

Do not edit the contact fields, ids, validation, or the more-information field set. Keep `v-if="mode === 'create'"`. Keep Footer last.

The create-mode template order must be:

1. basic info
2. contact block (`#customer-contact-name` etc.)
3. `Collapsible` / `#customer-more-info-trigger`
4. `DialogFooter`

Also change the spec status line from `草案，待用户书面审阅` to `已确认`.

### Step 4: Re-run the dialog suite

Run:

```bash
cd CRM-Client && npm run test:unit -- --run src/components/dialogs/__tests__/CustomerFormDialog.test.ts
```

Expected: PASS, including the two new tests and existing create/edit save tests.

### Step 5: Commit

```bash
git add CRM-Client/src/components/dialogs/CustomerFormDialog.vue CRM-Client/src/components/dialogs/__tests__/CustomerFormDialog.test.ts docs/superpowers/specs/2026-09-15-customer-create-contact-order-collapsible-motion-design.md
git commit -m "fix(customer): place create contacts above more-info"
```

---

## Task 2: Restore Collapsible height motion

**Files:**
- Modify: `CRM-Client/tailwind.config.ts:305-326`
- Modify: `CRM-Client/src/components/dialogs/CustomerFormDialog.vue` 的 `<Collapsible>` / `<CollapsibleContent>`
- Modify: `CRM-Client/src/components/dialogs/__tests__/CustomerFormDialog.test.ts`
- Keep: `CRM-Client/src/components/ui/collapsible/CollapsibleContent.vue` unless a one-line class-merge fix is required to preserve `overflow-hidden`

**Interfaces:**

- Consumes: Reka `Collapsible` `unmountOnHide` (template: `unmount-on-hide`) and `--reka-collapsible-content-height`.
- Produces: `animate-collapsible-down` / `animate-collapsible-up` actually exist; dialog more-info content uses an inner layout wrapper; this dialog's collapsible does not unmount on hide.

### Step 1: Write a failing markup test for the inner wrapper

Add this next to the Task 1 tests:

```typescript
it('keeps more-information layout classes on an inner wrapper', async () => {
  vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
  vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
  const wrapper = mountCreate()
  await flushPromises()
  const content = wrapper.get('#customer-more-info-content')
  expect(content.classes()).not.toContain('grid')
  expect(content.get('.grid').exists()).toBe(true)
  wrapper.unmount()
})
```

Run:

```bash
cd CRM-Client && npm run test:unit -- --run src/components/dialogs/__tests__/CustomerFormDialog.test.ts
```

Expected: FAIL because `#customer-more-info-content` currently has `class="grid gap-4 px-1 pt-1"`.

### Step 2: Add collapsible keyframes beside accordion

In `CRM-Client/tailwind.config.ts`, extend the existing `keyframes` / `animation` block. Keep `accordion-down/up` unchanged. Add:

```typescript
'collapsible-down': {
  from: {
    height: '0',
  },
  to: {
    height: 'var(--reka-collapsible-content-height)',
  },
},
'collapsible-up': {
  from: {
    height: 'var(--reka-collapsible-content-height)',
  },
  to: {
    height: '0',
  },
},
```

and:

```typescript
'collapsible-down': 'collapsible-down 0.2s ease-out',
'collapsible-up': 'collapsible-up 0.2s ease-out',
```

Do not replace accordion keyframes. Duration must stay `0.2s ease-out`.

### Step 3: Fix the dialog Collapsible markup

Replace the current collapsible opening with:

```vue
<Collapsible
  :open="moreInfoOpen"
  :unmount-on-hide="false"
  class="space-y-3 border-t border-slate-200 pt-4"
  @update:open="handleMoreInfoChange"
>
  <CollapsibleTrigger as-child>
    <button
      id="customer-more-info-trigger"
      type="button"
      class="flex h-input-mobile min-h-input-mobile w-full items-center justify-between rounded-wolf-lg border border-blue-200 bg-blue-50/60 px-3 text-left text-sm font-semibold text-blue-900"
      :aria-expanded="moreInfoOpen"
      aria-controls="customer-more-info-content"
    >
      <span>{{ moreInfoOpen ? '收起更多客户信息' : '更多客户信息' }}</span>
      <span class="text-xs font-semibold text-blue-700">已填写 {{ moreInfoCount }} 项</span>
    </button>
  </CollapsibleTrigger>
  <CollapsibleContent id="customer-more-info-content">
    <div class="grid gap-4 px-1 pt-1">
```

Close with an extra `</div>` before `</CollapsibleContent>`. Do not put `grid` / `gap-4` on `CollapsibleContent` itself.

If Vue class fallthrough still strips `overflow-hidden` from `CRM-Client/src/components/ui/collapsible/CollapsibleContent.vue`, change that file to merge classes the same way `AccordionContent.vue` does (`cn('overflow-hidden transition-all data-[state=closed]:animate-collapsible-up data-[state=open]:animate-collapsible-down', props.class)` with an inner slot wrapper). Prefer not changing the wrapper if the dialog no longer passes a layout class.

### Step 4: Re-run focused tests

Run:

```bash
cd CRM-Client && npm run test:unit -- --run src/components/dialogs/__tests__/CustomerFormDialog.test.ts
```

Expected: PASS.

### Step 5: Commit

```bash
git add CRM-Client/tailwind.config.ts CRM-Client/src/components/dialogs/CustomerFormDialog.vue CRM-Client/src/components/dialogs/__tests__/CustomerFormDialog.test.ts
git add CRM-Client/src/components/ui/collapsible/CollapsibleContent.vue
git commit -m "fix(customer): animate more-info collapsible height"
```

Only stage `CollapsibleContent.vue` if Task 2 actually changed it.

---

## Self-Review Checklist

- [x] Create-mode contact order is covered.
- [x] Edit mode stays without a contact block.
- [x] Collapsible keyframes use `--reka-collapsible-content-height` and 0.2s ease-out.
- [x] Layout class moves to an inner wrapper; `unmount-on-hide="false"` is specified.
- [x] No Accordion swap, no second animation system, no save-contract changes.
- [x] No keyframe snapshot tests.
- [x] Focused Vitest command is explicit.

## Handoff

Plan complete and saved to `docs/superpowers/plans/2026-09-15-customer-create-contact-order-collapsible-motion-plan.md`.
