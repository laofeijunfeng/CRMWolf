# 工作流节点选择器与画布改造 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 将 `/settings/approval-flows-new` 的工作流编辑器从左侧平铺节点改造成参考图风格的主画布：节点之间显示“＋”插入入口，分类节点库弹窗承载可扩展节点，并新增创建客户、创建联系人、创建商机三个独立 CRM 节点的 DSL 配置能力。

**Architecture:** 先把插入上下文和图变换抽成纯 TypeScript 图编辑原语，保证 between-edge、after-node、root 三种插入行为可独立测试；再用自定义 Vue Flow 边渲染“＋”插入槽，并用 shadcn-vue Dialog/Command 实现分类搜索节点库。WorkflowEditor 负责状态、选中节点和保存，节点注册表负责类型元数据与配置面板，后端 `workflow_dsl.py` 继续作为独立白名单和配置校验边界。新增 CRM 节点只持久化 DSL，不在本计划实现实际业务写入或 Activepieces 同步。

**Tech Stack:** Vue 3 + TypeScript + `@vue-flow/core` 1.48.x + shadcn-vue/Reka UI Dialog/Command + Vitest；FastAPI/Python + Pydantic 边界 + pytest。

## Global Constraints

- 不触碰其他未提交工作区改动；每个任务只暂存并提交自己负责的文件。
- 前端禁止新增 `any`、`as any`、`@ts-ignore` 和非必要非空断言。
- DSL 顶层结构固定为 `schema_version: 1`, `nodes`, `edges`；新增能力只扩展节点 `type` 和 `config`。
- 节点类型 key 必须在前端 `WORKFLOW_NODE_REGISTRY` 与后端 `NODE_CONFIG_REQUIREMENTS` 中一致。
- 不实现 Activepieces Adapter、执行、重试、运行历史、连接器市场或 CRM 业务写入 API。
- 保留现有五个节点、保存 API、乐观锁、409/422 错误处理、团队权限和旧 `/settings/approval-flows` 行为。
- 新增浮层遵循 `CRM-Docs/design-system/components/modal-sheet.md` 与 `overlay.md`：有标题、关闭按钮、Esc 关闭、焦点回收、窄屏内部滚动。
- 每个任务完成后运行该任务覆盖测试；跳过全量 lint（仓库存在既有 lint 问题）。
- 实现任务按顺序执行；`WorkflowEditor.vue` 的集成边界不可并行修改。

## File Boundaries and Interfaces

### New files

- `CRM-Client/src/components/workflow/workflowGraphEditing.ts`: pure graph-editing functions and `WorkflowInsertContext`; no Vue dependency.
- `CRM-Client/src/components/workflow/__tests__/workflowGraphEditing.test.ts`: graph insertion, edge splitting, and root-position tests.
- `CRM-Client/src/components/workflow/WorkflowNodePickerDialog.vue`: category/search/disabled-reason picker; never mutates graph directly.
- `CRM-Client/src/components/workflow/__tests__/WorkflowNodePickerDialog.test.ts`: rendering, filtering, trigger disable, select, and close behavior.
- `CRM-Client/src/components/workflow/WorkflowInsertEdge.vue`: Vue Flow custom edge that renders an accessible plus insertion button.
- `CRM-Client/src/components/workflow/__tests__/WorkflowInsertEdge.test.ts`: edge midpoint button and aria contract.
- `CRM-Client/src/components/workflow/nodeConfigPanels/ActionCreateCustomerPanel.vue`: customer creation DSL form.
- `CRM-Client/src/components/workflow/nodeConfigPanels/ActionCreateContactPanel.vue`: contact creation DSL form.
- `CRM-Client/src/components/workflow/nodeConfigPanels/ActionCreateOpportunityPanel.vue`: opportunity creation DSL form.
- `CRM-Client/src/components/workflow/__tests__/CRMNodeConfigPanels.test.ts`: public config-update contracts for the three panels.

### Modified files

- `CRM-Client/src/components/workflow/workflowNodeRegistry.ts`: add `crm` category and three CRM node definitions.
- `CRM-Client/src/components/workflow/workflowValidation.ts`: retain registry-driven required-field validation and add only required type-specific checks.
- `CRM-Client/src/components/workflow/WorkflowEditor.vue`: remove fixed left palette, integrate insertion contexts, picker, custom edges, root entry, right panel, and visual status.
- `CRM-Client/src/components/workflow/WorkflowNode.vue`: add category/status badges and selected/error presentation.
- `CRM-Client/src/components/workflow/__tests__/WorkflowEditor.test.ts`: replace palette assertions and cover root/terminal/between-edge insertion, picker selection, and DSL save shape.
- `CRM-Client/src/components/workflow/__tests__/workflowNodeRegistry.test.ts`: register the three CRM nodes.
- `CRM-Client/src/components/workflow/__tests__/workflowValidation.test.ts`: validate minimal valid and missing-field CRM configs.
- `CRM-Server/app/services/workflow_dsl.py`: add the three CRM node types and required fields.
- `CRM-Server/tests/unit/test_workflow_dsl.py`: add valid and missing-field cases for the three CRM types.
- `CRM-Server/tests/unit/api/test_workflows_api.py`: extend the existing `VALID_DSL`/CRUD boundary cases with a CRM-node payload round trip.

---

### Task 1: Extract graph insertion and edge transformation primitives

**Files:**
- Create: `CRM-Client/src/components/workflow/workflowGraphEditing.ts`
- Create: `CRM-Client/src/components/workflow/__tests__/workflowGraphEditing.test.ts`
- Modify: `CRM-Client/src/components/workflow/WorkflowEditor.vue:16-145`
- Modify: `CRM-Client/src/components/workflow/__tests__/WorkflowEditor.test.ts:99-171`

**Interfaces:**

```ts
export interface WorkflowInsertContext {
  kind: 'between-edge' | 'after-node' | 'root'
  sourceNodeId?: string
  targetNodeId?: string
  edgeId?: string
}

export function insertNodeIntoGraph(
  nodes: WorkflowEditorNode[],
  edges: WorkflowEditorEdge[],
  node: WorkflowEditorNode,
  context: WorkflowInsertContext,
): { nodes: WorkflowEditorNode[]; edges: WorkflowEditorEdge[] }

export function getTerminalInsertContexts(
  nodes: WorkflowEditorNode[],
  edges: WorkflowEditorEdge[],
): WorkflowInsertContext[]

export function getEdgeInsertContext(edge: WorkflowEditorEdge): WorkflowInsertContext
```

`WorkflowEditorNode` and `WorkflowEditorEdge` must be exported structural types containing only editor graph data. Functions must not mutate input arrays.

- `between-edge`: remove exactly the referenced edge; add source → new node and new node → target; preserve unrelated edges.
- `after-node`: add source → new node; preserve all existing edges.
- `root`: add node without an edge.
- Missing or invalid context returns the original graph unchanged.

**Steps:**

- [ ] Write failing tests for `between-edge`, `after-node`, `root`, invalid context, and multiple terminal contexts.
- [ ] Run `cd CRM-Client && npm run test:unit -- --run src/components/workflow/__tests__/workflowGraphEditing.test.ts`; expected failure because the module/functions do not exist.
- [ ] Implement pure graph functions and shared structural types.
- [ ] Replace `WorkflowEditor.addNode`’s current sole-tail guess with explicit context-based insertion; retain a root path until Task 2 wires UI contexts.
- [ ] Update editor tests so auto-tail coverage uses explicit `after-node` context while manual `onConnect` behavior remains covered.
- [ ] Run graph and editor tests; expected all pass.
- [ ] Commit only Task 1 files with `feat(workflow): add graph insertion primitives`.

---

### Task 2: Add plus insertion slots and categorized node picker

**Files:**
- Create: `CRM-Client/src/components/workflow/WorkflowNodePickerDialog.vue`
- Create: `CRM-Client/src/components/workflow/__tests__/WorkflowNodePickerDialog.test.ts`
- Create: `CRM-Client/src/components/workflow/WorkflowInsertEdge.vue`
- Create: `CRM-Client/src/components/workflow/__tests__/WorkflowInsertEdge.test.ts`
- Modify: `CRM-Client/src/components/workflow/WorkflowEditor.vue:1-304`
- Modify: `CRM-Client/src/components/workflow/__tests__/WorkflowEditor.test.ts`
- Delete after import migration: `CRM-Client/src/components/workflow/WorkflowNodePalette.vue` if no references remain.

**Interfaces:**

```ts
const props = defineProps<{
  open: boolean
  nodeTypes: readonly WorkflowNodePickerItem[]
  triggerUsed: boolean
}>()
const emit = defineEmits<{
  'update:open': [open: boolean]
  select: [type: WorkflowNodeType]
}>()
```

`WorkflowNodePickerItem` includes `type`, `label`, `description`, `category`, `icon`, `isTrigger`, and optional `disabledReason`.

```ts
export interface WorkflowInsertEdgeData {
  insertionContext: WorkflowInsertContext
}

const props = defineProps<EdgeProps<WorkflowInsertEdgeData>>()
const emit = defineEmits<{ insert: [edgeId: string] }>()
```

The custom edge uses supported Vue Flow path/label primitives, renders one keyboard-focusable button at the edge midpoint, exposes `aria-label="在此处添加节点"`, and uses `data-testid="workflow-insert-edge-${id}"`.

**Steps:**

- [ ] Write picker tests for categories, search by label/description/type, trigger disable reason, select event, and Escape/close.
- [ ] Run the picker test alone and confirm red.
- [ ] Implement the Dialog with the existing Dialog and Command primitives; keep focus and mobile scrolling inside the dialog.
- [ ] Write custom-edge tests for button, label, and emitted edge ID.
- [ ] Implement `WorkflowInsertEdge.vue` and register an editor-local `edgeTypes` map.
- [ ] Add `insertContext`, `pickerOpen`, and `openPicker(context)` to the editor; route selection through Task 1’s graph function and select the new node.
- [ ] Pass insertion context through edge `data` without changing persisted DSL edge shape.
- [ ] Add a toolbar `添加节点` root entry using the same picker.
- [ ] Add terminal insertion buttons; in multiple-branch graphs derive one context per concrete edge and never choose by array order.
- [ ] Run picker, edge, and editor tests; expected all pass.
- [ ] Commit with `feat(workflow): add categorized node picker and insert slots`.

---

### Task 3: Add independent CRM node types and configuration panels

**Files:**
- Create: `CRM-Client/src/components/workflow/nodeConfigPanels/ActionCreateCustomerPanel.vue`
- Create: `CRM-Client/src/components/workflow/nodeConfigPanels/ActionCreateContactPanel.vue`
- Create: `CRM-Client/src/components/workflow/nodeConfigPanels/ActionCreateOpportunityPanel.vue`
- Create: `CRM-Client/src/components/workflow/__tests__/CRMNodeConfigPanels.test.ts`
- Modify: `CRM-Client/src/components/workflow/workflowNodeRegistry.ts`
- Modify: `CRM-Client/src/components/workflow/__tests__/workflowNodeRegistry.test.ts`
- Modify: `CRM-Client/src/components/workflow/__tests__/workflowValidation.test.ts`

**Interfaces:**

Add exact keys:

```text
crm.create_customer
crm.create_contact
crm.create_opportunity
```

Each panel accepts `config: Record<string, unknown>` and emits:

```ts
'update:config': [patch: Record<string, unknown>]
```

Defaults and required fields:

```text
crm.create_customer
  defaults: account_name='', city='', industry='', address='', company_scale='', owner_strategy='creator', default_procurement_method_id=null
  required: account_name, city

crm.create_contact
  defaults: customer_ref='', name='', gender='1', position='', mobile='', is_decision_maker=false, email='', wechat_id='', remark=''
  required: customer_ref, name, gender, position, mobile

crm.create_opportunity
  defaults: customer_ref='', opportunity_name='', total_amount=0, user_count=1, license_type='SUBSCRIPTION', subscription_years=1, purchase_type='NEW', expected_closing_date='', decision_maker_count=null, procurement_method_id=null, procurement_stage_id=null, owner_strategy='creator'
  required: customer_ref, total_amount, user_count, license_type, purchase_type, expected_closing_date
```

Panels only edit DSL config; they must not call business creation APIs.

**Steps:**

- [ ] Add failing registry tests for keys, categories, labels, defaults, required fields, icons, and summaries.
- [ ] Run the registry test and confirm failure.
- [ ] Add registry metadata with existing form primitives and installed Lucide icons.
- [ ] Add panel tests that update required fields through public emitted patches and assert no business API calls.
- [ ] Implement customer, contact, and opportunity panels with the exact defaults/required fields above.
- [ ] Add validation tests for missing required values and valid minimal configs.
- [ ] Run registry, panel, validation, and editor tests; expected all pass.
- [ ] Commit with `feat(workflow): add CRM resource node definitions`.

---

### Task 4: Synchronize backend DSL registry and validation

**Files:**
- Modify: `CRM-Server/app/services/workflow_dsl.py:3-13`
- Modify: `CRM-Server/tests/unit/test_workflow_dsl.py:1-60`
- Modify: `CRM-Server/tests/unit/api/test_workflows_api.py:30-52`

**Interfaces:**

Extend existing constants without changing their public names:

```python
NODE_CONFIG_REQUIREMENTS.update({
    "crm.create_customer": ["account_name", "city"],
    "crm.create_contact": ["customer_ref", "name", "gender", "position", "mobile"],
    "crm.create_opportunity": [
        "customer_ref", "total_amount", "user_count", "license_type",
        "purchase_type", "expected_closing_date",
    ],
})
```

`KNOWN_NODE_TYPES` and `TRIGGER_TYPES` remain derived from `NODE_CONFIG_REQUIREMENTS`; no API schema or database migration is needed.

**Steps:**

- [ ] Add failing unit tests for one valid DSL containing each CRM node and one missing-field case per node.
- [ ] Add a backend API test posting a valid CRM-node DSL and assert 201, node count, and round-tripped DSL.
- [ ] Run `cd CRM-Server && pytest tests/unit/test_workflow_dsl.py tests/unit/api/test_workflows_api.py -q`; expected new tests fail before registry update.
- [ ] Add the three requirements to `NODE_CONFIG_REQUIREMENTS`; retain existing operator/notify validation and graph rules.
- [ ] Run the same focused pytest command; expected all pass.
- [ ] Commit with `feat(workflow): register CRM nodes in DSL validator`.

---

### Task 5: Apply reference visual hierarchy and responsive editor shell

**Files:**
- Modify: `CRM-Client/src/components/workflow/WorkflowEditor.vue:250-304`
- Modify: `CRM-Client/src/components/workflow/WorkflowNode.vue:11-24`
- Modify: `CRM-Client/src/components/workflow/__tests__/WorkflowEditor.test.ts`
- Modify: `CRM-Client/src/components/workflow/__tests__/WorkflowNode.test.ts`
- Inspect: `CRM-Docs/design-system/foundations/responsive-mobile.md`, `CRM-Docs/design-system/foundations/radius-elevation.md`

**Interfaces:**

No persisted-data or public API changes. Keep existing `saved`, `cancelled`, `save`, `reload`, `nodes`, and `edges` exposed contracts.

**Steps:**

- [ ] Add tests for top status text, root `添加节点` control, selected-node panel close behavior, category badge/summary, and error-state rendering.
- [ ] Implement the reference hierarchy: top workflow/status toolbar, canvas as primary area, right configuration panel with independent scrolling, bottom Vue Flow controls.
- [ ] Add explicit draft/unsaved/validation status copy without changing publish API semantics.
- [ ] Add category/status badges and stable `aria-label` values to node cards and insertion buttons.
- [ ] Add narrow viewport classes so the configuration panel becomes a non-horizontal-scrolling sheet/drawer-like column.
- [ ] Run focused workflow component tests and `npm run type-check`; report any pre-existing unrelated type errors separately.
- [ ] Commit with `feat(workflow): refine canvas visual hierarchy`.

---

### Task 6: End-to-end browser smoke and integration cleanup

**Files:**
- Modify: `CRM-Client/src/components/workflow/__tests__/WorkflowEditor.test.ts` only if a missing consumer-visible regression is found.
- Modify: `CRM-Client/src/views/__tests__/ApprovalFlowsNew.test.ts` only if the new editor mount contract changes.
- Delete: `CRM-Client/src/components/workflow/WorkflowNodePalette.vue` only after repository search proves no imports remain.
- Create only if required by existing conventions: a focused browser-smoke helper under an existing test/support directory, never at repo root.

**Interfaces:**

No new public API. Validate the complete user-visible path from `/settings/approval-flows-new` through saved `WorkflowDsl`.

**Steps:**

- [ ] Run focused frontend tests: `cd CRM-Client && npm run test:unit -- --run src/components/workflow/__tests__ src/views/__tests__/ApprovalFlowsNew.test.ts`.
- [ ] Launch/use the actual Vite page with browser tooling; create a blank workflow, add Trigger, click a concrete plus slot, search/select `创建客户`, configure required fields, add `创建联系人`, and inspect the rendered nodes/edges.
- [ ] Capture the save request or use the existing API mock boundary and assert the payload has `schema_version: 1`, both CRM node types, and the expected split/append edges.
- [ ] Reopen the saved workflow through the mocked/real detail path and assert node type, config, and edge round trip.
- [ ] Run `git diff --check` and the focused backend pytest command from Task 4.
- [ ] Search for remaining `WorkflowNodePalette` imports; delete the obsolete file only if the search is empty.
- [ ] Run `npm run type-check`; distinguish existing unrelated diagnostics from feature diagnostics.
- [ ] Commit any final cleanup with `chore(workflow): remove obsolete node palette` only when deletion is proven safe.

---

## Self-review checklist

- Spec coverage: Tasks 1–2 cover the canvas, insertion contexts, dialog, focus, search, and edge splitting; Task 3 covers independent CRM nodes and panels; Task 4 covers backend DSL parity; Task 5 covers visual/accessibility/responsive requirements; Task 6 covers the browser acceptance path and cleanup.
- Placeholder scan: no `TBD`, `TODO`, or unspecified implementation steps; every step names files, commands, expected behavior, and interfaces.
- Type consistency: `WorkflowInsertContext`, `insertNodeIntoGraph`, picker props/emits, edge props/emits, node type keys, defaults, and backend requirements are named consistently across tasks.
- Scope: runtime CRM writes and Activepieces remain explicitly excluded; no migration is needed because DSL JSON shape is unchanged.
