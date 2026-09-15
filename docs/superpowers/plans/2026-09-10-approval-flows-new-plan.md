# 审批流程管理新页面 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `/settings/approval-flows-new` 从旧审批 Sheet 预览改为独立的、可加载和可操作的审批流程列表页，同时继续复用现有传统审批 API 与表单。

**Architecture:** `SettingsModulePage.vue` 为新模块挂载独立的 `ApprovalFlowsNew.vue`。页面自行管理列表加载、页面状态、启停和表单打开状态；`ApprovalFlowFormDialog.vue` 继续负责新建/编辑表单、校验和提交。旧 `/settings/approval-flows` 不变。

**Tech Stack:** Vue 3 Composition API、TypeScript、shadcn-vue、Vitest、现有 `approvalFlowApi`、现有权限与错误处理工具。

## Global Constraints

- 新页面必须使用 V2 设计规范、shadcn-vue 语义类和现有 UI 组件模式。
- 不新增 Element Plus、旧 SCSS token、`variables.scss` 或 `wolf-design.scss`。
- 不使用 `any`、`as any`、`@ts-ignore` 或不必要的非空断言。
- 页面使用现有 `ApprovalFlowDetail` 和 `approvalFlowApi`，不创建平行审批流程 API 模型。
- `/settings/approval-flows` 的现有行为保持不变。
- 本阶段不实现 Vue Flow、Automation DSL 持久化、Activepieces 同步、业务事件、`create_follow_up_task`、运行历史或审计接入。
- 没有 API 字段时显示“暂未接入”，不得伪造运行结果、同步结果或更新时间。
- 列表 API 失败时保留原列表展示状态，不乐观修改流程状态。

---

## 文件结构与职责

- Create: `CRM-Client/src/views/ApprovalFlowsNew.vue` — 独立页面、列表状态、卡片展示、启停、新建/编辑入口。
- Modify: `CRM-Client/src/views/SettingsModulePage.vue:85-103` — 将 `approval-flows-new` 动态组件从旧 Sheet 改为新页面，并更新迁移描述。
- Create: `CRM-Client/src/views/__tests__/ApprovalFlowsNew.test.ts` — 覆盖列表、空态、错误重试、表单入口和启停行为。
- Existing reference: `CRM-Client/src/api/approvalFlow.ts` — 复用 `ApprovalFlowDetail` 与 `approvalFlowApi`。
- Existing reference: `CRM-Client/src/components/system-config/ApprovalFlowFormDialog.vue` — 复用创建/编辑表单，不复制内部字段逻辑。
- Existing reference: `CRM-Client/src/components/system-config/ApprovalFlowSheet.vue` — 仅参考业务类型标签、确认和错误处理模式；不修改旧页面行为。

---

### Task 1: 为独立页面建立行为测试

**Files:**
- Create: `CRM-Client/src/views/__tests__/ApprovalFlowsNew.test.ts`
- Reference: `CRM-Client/src/api/approvalFlow.ts`
- Reference: `CRM-Client/src/components/system-config/ApprovalFlowFormDialog.vue`

**Interfaces:**
- Consumes the page contract: `ApprovalFlowsNew.vue` renders the existing `ApprovalFlowDetail` records and exposes create/edit/toggle actions through visible controls.
- Produces the observable test contract used by Task 2: the page calls `getApprovalFlows`, opens `ApprovalFlowFormDialog` with `mode` and `flow-id`, and calls `updateApprovalFlow` with only the target flow's `is_active` field after confirmation.

- [ ] **Step 1: Add test fixtures and API mocks**

Use typed fixtures with numeric IDs, one active flow and one inactive flow. Mock `@/api/approvalFlow`, `@/utils/errorHandler`, and the form dialog. The form-dialog stub must expose received props and emit `success` so the test verifies the public page behavior rather than the form internals.

```ts
const activeFlow: ApprovalFlowDetail = {
  id: 11,
  flow_name: '合同审批',
  flow_code: 'CONTRACT_DEFAULT',
  description: '合同默认审批流程',
  business_type: 'contract',
  is_active: 1,
  nodes: [],
}
```

Adapt the fixture to the exact required fields in the existing `ApprovalFlowDetail` type; do not use `any`.

- [ ] **Step 2: Write the success, empty, and error tests**

The tests must assert visible consumer behavior:

```ts
it('renders loaded flow identity, business type, and status', async () => {
  getApprovalFlows.mockResolvedValue([activeFlow])
  const wrapper = mountPage()

  await vi.waitFor(() => expect(wrapper.text()).toContain('合同审批'))

  expect(wrapper.text()).toContain('启用')
  expect(wrapper.text()).toContain('合同')
  expect(wrapper.text()).toContain('最近运行：暂未接入')
  expect(wrapper.text()).toContain('Activepieces：暂未接入')
})

it('shows the empty state and create action for an empty response', async () => {
  getApprovalFlows.mockResolvedValue([])
  const wrapper = mountPage()

  await vi.waitFor(() => expect(wrapper.text()).toContain('暂无审批流程'))
  expect(wrapper.get('[data-testid="approval-flows-create"]').exists()).toBe(true)
})

it('shows retry action after load failure and retries the request', async () => {
  getApprovalFlows.mockRejectedValueOnce(new Error('network'))
    .mockResolvedValueOnce([activeFlow])
  const wrapper = mountPage()

  await vi.waitFor(() => expect(wrapper.text()).toContain('加载审批流程失败'))
  await wrapper.get('[data-testid="approval-flows-retry"]').trigger('click')
  await vi.waitFor(() => expect(getApprovalFlows).toHaveBeenCalledTimes(2))
  expect(wrapper.text()).toContain('合同审批')
})
```

- [ ] **Step 3: Write create, edit, and toggle tests**

Verify that create opens the form with `mode="create"`, edit passes the numeric flow ID, and toggle confirmation calls the API with only `{ is_active: 0 }` (or `1` for inactive records), then reloads the list.

```ts
it('opens create and edit with the expected form props', async () => {
  getApprovalFlows.mockResolvedValue([activeFlow])
  const wrapper = mountPage()
  await vi.waitFor(() => expect(wrapper.text()).toContain('合同审批'))

  await wrapper.get('[data-testid="approval-flows-create"]').trigger('click')
  expect(wrapper.getComponent({ name: 'ApprovalFlowFormDialog' }).props('mode')).toBe('create')

  await wrapper.get('[data-testid="approval-flow-edit-11"]').trigger('click')
  const form = wrapper.getComponent({ name: 'ApprovalFlowFormDialog' })
  expect(form.props('mode')).toBe('edit')
  expect(form.props('flowId')).toBe(11)
})

it('confirms a toggle, updates only the target status, and reloads', async () => {
  getApprovalFlows.mockResolvedValue([activeFlow])
  updateApprovalFlow.mockResolvedValue({ ...activeFlow, is_active: 0 })
  confirmDialog.mockResolvedValue(true)
  const wrapper = mountPage()
  await vi.waitFor(() => expect(wrapper.text()).toContain('合同审批'))

  await wrapper.get('[data-testid="approval-flow-toggle-11"]').trigger('click')

  await vi.waitFor(() => expect(updateApprovalFlow).toHaveBeenCalledWith(11, { is_active: 0 }))
  expect(getApprovalFlows).toHaveBeenCalledTimes(2)
})
```

- [ ] **Step 4: Add form-success refresh and toggle-failure assertions**

Emit `success` from the form stub and assert `getApprovalFlows` is called again. Make `updateApprovalFlow` reject, assert the error handler is called, and assert the original `启用` label remains visible.

- [ ] **Step 5: Run the focused test before implementation**

Run:

```bash
cd CRM-Client
npm run test:unit -- --run src/views/__tests__/ApprovalFlowsNew.test.ts
```

Expected: FAIL because `ApprovalFlowsNew.vue` does not exist yet.

---

### Task 2: Implement the independent approval-flow page

**Files:**
- Create: `CRM-Client/src/views/ApprovalFlowsNew.vue`
- Modify: `CRM-Client/src/views/SettingsModulePage.vue:85-103`

**Interfaces:**
- Consumes: `approvalFlowApi.getApprovalFlows`, `approvalFlowApi.updateApprovalFlow`, `ApprovalFlowDetail`, `ApprovalFlowFormDialog`, `confirmDialog`, and `handleApiError`.
- Produces: a page component with visible `data-testid` hooks used by Task 1: `approval-flows-create`, `approval-flows-retry`, `approval-flow-edit-{id}`, and `approval-flow-toggle-{id}`.

- [ ] **Step 1: Create the page state and typed helpers**

Implement `<script setup lang="ts">` with these state types and values:

```ts
const flows = ref<ApprovalFlowDetail[]>([])
const loading = ref(false)
const errorMessage = ref<string | null>(null)
const formOpen = ref(false)
const formMode = ref<'create' | 'edit'>('create')
const editingFlowId = ref<number | null>(null)
const togglingFlowId = ref<number | null>(null)
```

Add a typed business-type label map matching the existing approval-flow labels. Add a guard that filters list data to records with numeric IDs before rendering actions; keep the original typed records for display.

- [ ] **Step 2: Implement the single list loader**

Implement `loadFlows(): Promise<void>`:

```ts
async function loadFlows(): Promise<void> {
  loading.value = true
  errorMessage.value = null
  try {
    const data = await approvalFlowApi.getApprovalFlows()
    flows.value = Array.isArray(data) ? data : []
  } catch (error: unknown) {
    errorMessage.value = '加载审批流程失败，请稍后重试。'
    handleApiError(error, '获取审批流程')
  } finally {
    loading.value = false
  }
}
```

Call it once on mount. Do not mutate `flows` optimistically on toggle failure.

- [ ] **Step 3: Implement create/edit and toggle actions**

Create handlers:

```ts
function openCreate(): void {
  formMode.value = 'create'
  editingFlowId.value = null
  formOpen.value = true
}

function openEdit(flowId: number): void {
  formMode.value = 'edit'
  editingFlowId.value = flowId
  formOpen.value = true
}

async function toggleFlow(flow: ApprovalFlowDetail & { id: number }): Promise<void> {
  if (togglingFlowId.value !== null) return
  const nextActive = flow.is_active === 1 ? 0 : 1
  const action = nextActive === 1 ? '启用' : '停用'
  const confirmed = await confirmDialog(`确定${action}“${flow.flow_name}”吗？`)
  if (!confirmed) return

  togglingFlowId.value = flow.id
  try {
    await approvalFlowApi.updateApprovalFlow(flow.id, { is_active: nextActive })
    await loadFlows()
  } catch (error: unknown) {
    handleApiError(error, `${action}审批流程`)
  } finally {
    togglingFlowId.value = null
  }
}
```

Use the repository's actual `confirmDialog` return contract if it differs; preserve the invariant that the API payload contains only `is_active`.

- [ ] **Step 4: Implement the V2 page template**

Use the existing `Card`, `Button`, `Badge`/status component, and semantic utility classes. Render:

- Header title `审批流程管理`;
- Description explaining this is the CRM-side configuration preview;
- `手动创建` button with `data-testid="approval-flows-create"`;
- Loading state;
- Error state with `data-testid="approval-flows-retry"`;
- Empty state text `暂无审批流程` and create action;
- One card per numeric-ID flow;
- Flow name, code, business type, description fallback `暂无描述`, node count, active/inactive status;
- `最近运行：暂未接入` and `Activepieces：暂未接入`;
- Edit and toggle buttons with deterministic test IDs and accessible labels;
- Disabled state for the active row while toggling.

Do not render API fields that do not exist as fabricated values.

- [ ] **Step 5: Rewire only the new module mount**

In `SettingsModulePage.vue`, change only the `approval-flows-new` entry:

```ts
'approval-flows-new': defineAsyncComponent(() => import('@/views/ApprovalFlowsNew.vue')),
```

Keep `approval-flows` mapped to `ApprovalFlowSheet.vue`. Update the migration description to state that the new page now has an independent list experience while its form still uses existing approval APIs. Remove the obsolete empty-description wording for the new page only if the page itself now handles its own empty state; do not change unrelated module descriptions.

- [ ] **Step 6: Run focused tests and type-check**

Run:

```bash
cd CRM-Client
npm run test:unit -- --run src/views/__tests__/ApprovalFlowsNew.test.ts src/settingsNavigation.test.ts
npm run type-check
```

Expected: focused tests pass and type-check exits successfully. Existing unrelated lint warnings/errors are not part of this task.

- [ ] **Step 7: Run diff hygiene check**

Run:

```bash
git diff --check
```

Expected: no output and exit code 0.

---

### Task 3: Review the finished page against the approved design

**Files:**
- Review: `CRM-Client/src/views/ApprovalFlowsNew.vue`
- Review: `CRM-Client/src/views/SettingsModulePage.vue`
- Review: `CRM-Client/src/views/__tests__/ApprovalFlowsNew.test.ts`

- [ ] **Step 1: Verify the approved non-goals remain absent**

Confirm the diff does not add Vue Flow, Automation DSL persistence, Activepieces API calls, webhook delivery, business-event code, `create_follow_up_task`, run-history data, or old-route replacement.

- [ ] **Step 2: Verify state and permission boundaries**

Confirm the page remains mounted through `SettingsModulePage.vue`, which continues to enforce existing settings access. Confirm create/edit/toggle controls do not bypass the existing permission contract.

- [ ] **Step 3: Re-run the covering commands**

Run:

```bash
cd CRM-Client
npm run test:unit -- --run src/views/__tests__/ApprovalFlowsNew.test.ts src/settingsNavigation.test.ts
npm run type-check
git diff --check
```

Expected: all focused tests pass, type-check passes, and diff check is clean.

- [ ] **Step 4: Commit the implementation**

```bash
git add CRM-Client/src/views/ApprovalFlowsNew.vue CRM-Client/src/views/SettingsModulePage.vue CRM-Client/src/views/__tests__/ApprovalFlowsNew.test.ts
 git commit -m "feat(client): add independent approval flow list"
```

Do not stage unrelated existing worktree changes.
