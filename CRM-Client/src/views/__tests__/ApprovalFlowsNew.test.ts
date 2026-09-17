import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, h, type VNode } from 'vue'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ApprovalFlowListItem } from '@/api/approvalFlow'
import type { WorkflowSummary } from '@/api/workflow'
import { usePermissionStore } from '@/stores/permissions'
import { useHeaderStore } from '@/stores/header'

const mocks = vi.hoisted(() => ({
  getApprovalFlows: vi.fn(),
  updateApprovalFlow: vi.fn(),
  listWorkflows: vi.fn(),
  updateWorkflowStatus: vi.fn(),
  confirmDialog: vi.fn(),
  handleApiError: vi.fn(),
}))

vi.mock('@/api/approvalFlow', () => ({
  default: {
    getApprovalFlows: mocks.getApprovalFlows,
    updateApprovalFlow: mocks.updateApprovalFlow,
  },
}))
vi.mock('@/api/workflow', () => ({
  default: {
    list: mocks.listWorkflows,
    updateStatus: mocks.updateWorkflowStatus,
  },
}))

vi.mock('@/utils/confirmDialog', () => ({
  confirmDialog: mocks.confirmDialog,
}))

vi.mock('@/utils/errorHandler', () => ({
  handleApiError: mocks.handleApiError,
}))

vi.mock('@/components/system-config/ApprovalFlowFormDialog.vue', () => ({
  default: defineComponent({
    name: 'ApprovalFlowFormDialog',
    props: {
      open: { type: Boolean, required: true },
      mode: { type: String, required: true },
      flowId: { type: Number, default: null },
    },
    emits: ['update:open', 'success'],
    setup(props, { emit }): () => VNode | null {
      return () => props.open
        ? h('div', { 'data-testid': 'approval-flow-form-dialog' }, [
            h('span', { 'data-testid': 'approval-flow-form-mode' }, props.mode),
            h('span', { 'data-testid': 'approval-flow-form-id' }, String(props.flowId ?? '')),
            h('button', { 'data-testid': 'approval-flow-form-success', onClick: () => emit('success') }, '保存'),
          ])
        : null
    },
  }),
}))
vi.mock('@/components/workflow/WorkflowEditor.vue', () => ({
  default: defineComponent({
    name: 'WorkflowEditor',
    props: { workflowId: { type: Number, default: null } },
    emits: ['saved', 'cancelled'],
    setup(props, { emit }): () => VNode {
      return () => h('div', { 'data-testid': 'workflow-editor' }, [
        h('span', { 'data-testid': 'workflow-editor-id' }, String(props.workflowId ?? '')),
        h('button', { 'data-testid': 'workflow-editor-save', onClick: () => emit('saved', {}) }, '保存工作流'),
        h('button', { 'data-testid': 'workflow-editor-cancel', onClick: () => emit('cancelled') }, '取消工作流'),
      ])
    },
  }),
}))

import ApprovalFlowsNew from '../ApprovalFlowsNew.vue'

const activeFlow: ApprovalFlowListItem = {
  id: 11,
  flow_name: '合同审批',
  flow_code: 'CONTRACT_DEFAULT',
  description: '合同默认审批流程',
  business_type: 'CONTRACT',
  is_active: 1,
  created_time: '2026-09-10T10:00:00Z',
  last_modified_time: '2026-09-10T10:00:00Z',
}

const inactiveFlow: ApprovalFlowListItem = {
  id: 12,
  flow_name: '回款审批',
  flow_code: 'PAYMENT_DEFAULT',
  description: '回款审批流程',
  business_type: 'PAYMENT',
  is_active: 0,
  created_time: '2026-09-10T10:00:00Z',
  last_modified_time: '2026-09-10T10:00:00Z',
}
const draftWorkflow: WorkflowSummary = {
  id: 21,
  name: '商机跟进自动化',
  description: null,
  status: 'draft',
  node_count: 4,
  created_time: '2026-09-10T10:00:00Z',
  last_modified_time: '2026-09-10T10:00:00Z',
}
const publishedWorkflow: WorkflowSummary = { ...draftWorkflow, id: 23, name: '已发布自动化', status: 'published' }
const pausedWorkflow: WorkflowSummary = { ...draftWorkflow, id: 22, name: '暂停自动化', status: 'paused' }

function mountPage(permissionCodes: string[] = [
  'approval:flow:create',
  'approval:flow:edit',
  'approval:flow:view',
  'automation:create',
  'automation:edit',
  'automation:publish',
  'automation:read',
], props: { action?: 'create' | 'edit' | ''; recordId?: string } = {}): VueWrapper {
  const pinia = createPinia()
  setActivePinia(pinia)
  const permissionStore = usePermissionStore()
  permissionStore.permissions = permissionCodes.map((code, index) => ({
    id: index + 1,
    code,
    name: code,
    resource: code.split(':')[0] ?? '',
    action: code.split(':').slice(-1)[0] ?? '',
    scope: null,
    description: null,
  }))
  permissionStore.loadState = 'ready'
  permissionStore.initialized = true
  return mount(ApprovalFlowsNew, { props, global: { plugins: [pinia] } })
}

function mountPageBeforePermissionsReady(): VueWrapper {
  const pinia = createPinia()
  setActivePinia(pinia)
  const permissionStore = usePermissionStore()
  permissionStore.permissions = []
  permissionStore.loadState = 'idle'
  permissionStore.initialized = false
  return mount(ApprovalFlowsNew, { global: { plugins: [pinia] } })
}

function headerActionVisible(id: string): boolean {
  const action = useHeaderStore().actions.find((headerAction) => headerAction.id === id)
  return action !== undefined && action.visible !== false
}

async function triggerHeaderAction(id: string): Promise<void> {
  const action = useHeaderStore().actions.find((headerAction) => headerAction.id === id)
  expect(action).toBeDefined()
  action?.handler()
  await flushPromises()
}

async function waitForLoaded(wrapper: VueWrapper): Promise<void> {
  await vi.waitFor(() => expect(wrapper.text()).toContain('合同审批'))
}

describe('ApprovalFlowsNew', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.getApprovalFlows.mockResolvedValue([activeFlow])
    mocks.listWorkflows.mockResolvedValue([draftWorkflow])
    mocks.confirmDialog.mockResolvedValue(true)
  })
  it('loads both lists when permissions become ready after mount', async () => {
    const wrapper = mountPageBeforePermissionsReady()
    const permissionStore = usePermissionStore()

    expect(mocks.getApprovalFlows).not.toHaveBeenCalled()
    expect(mocks.listWorkflows).not.toHaveBeenCalled()

    permissionStore.permissions = ['approval:flow:view', 'automation:read'].map((code, index) => ({
      id: index + 1,
      code,
      name: code,
      resource: code.split(':')[0] ?? '',
      action: code.split(':').slice(-1)[0] ?? '',
      scope: null,
      description: null,
    }))
    permissionStore.loadState = 'ready'
    await vi.waitFor(() => {
      expect(mocks.getApprovalFlows).toHaveBeenCalledTimes(1)
      expect(mocks.listWorkflows).toHaveBeenCalledTimes(1)
    })
    wrapper.unmount()
  })

  it('opens the create form from an action prop', () => {
    const wrapper = mountPage(undefined, { action: 'create', recordId: '' })

    const form = wrapper.getComponent({ name: 'ApprovalFlowFormDialog' })
    expect(form.props('mode')).toBe('create')
    expect(form.props('flowId')).toBe(null)
  })

  it('opens the edit form from a valid action and recordId prop', () => {
    const wrapper = mountPage(undefined, { action: 'edit', recordId: '11' })

    const form = wrapper.getComponent({ name: 'ApprovalFlowFormDialog' })
    expect(form.props('mode')).toBe('edit')
    expect(form.props('flowId')).toBe(11)
  })

  it('renders loaded flow identity, business type, and status', async () => {
    const wrapper = mountPage()
    await waitForLoaded(wrapper)

    expect(wrapper.text()).toContain('启用')
    expect(wrapper.text()).toContain('合同')
    expect(wrapper.text()).toContain('Activepieces：暂未接入')
  })

  it('renders list records without node data as unavailable', async () => {
    const wrapper = mountPage()
    await waitForLoaded(wrapper)

    expect(wrapper.text()).toContain('合同审批')
    expect(wrapper.text()).toMatch(/节点数\s*暂未提供/)
  })

  it('shows the empty state and create action for an empty response', async () => {
    mocks.getApprovalFlows.mockResolvedValue([])
    const wrapper = mountPage()

    await vi.waitFor(() => expect(wrapper.text()).toContain('暂无审批流程'))
    expect(headerActionVisible('create-approval-flow')).toBe(true)
  })

  it('shows retry action after load failure and retries the request', async () => {
    mocks.getApprovalFlows.mockRejectedValueOnce(new Error('network')).mockResolvedValueOnce([activeFlow])
    const wrapper = mountPage()

    await vi.waitFor(() => expect(wrapper.text()).toContain('加载审批流程失败'))
    await wrapper.get('[data-testid="approval-flows-retry"]').trigger('click')
    await vi.waitFor(() => expect(mocks.getApprovalFlows).toHaveBeenCalledTimes(2))
    expect(wrapper.text()).toContain('合同审批')
    expect(mocks.handleApiError).toHaveBeenCalledWith(expect.any(Error), '获取审批流程')
  })

  it('opens create and edit with the expected form props', async () => {
    const wrapper = mountPage()
    await waitForLoaded(wrapper)

    await triggerHeaderAction('create-approval-flow')
    expect(wrapper.getComponent({ name: 'ApprovalFlowFormDialog' }).props('mode')).toBe('create')

    await wrapper.get('[data-testid="approval-flow-edit-11"]').trigger('click')
    const form = wrapper.getComponent({ name: 'ApprovalFlowFormDialog' })
    expect(form.props('mode')).toBe('edit')
    expect(form.props('flowId')).toBe(11)
  })

  it('confirms a toggle, updates only the target status, and reloads', async () => {
    mocks.updateApprovalFlow.mockResolvedValue({ ...activeFlow, is_active: 0 })
    const wrapper = mountPage()
    await waitForLoaded(wrapper)

    await wrapper.get('[data-testid="approval-flow-toggle-11"]').trigger('click')
    await vi.waitFor(() => expect(mocks.updateApprovalFlow).toHaveBeenCalledWith(11, { is_active: 0 }))
    expect(mocks.getApprovalFlows).toHaveBeenCalledTimes(2)
    expect(mocks.confirmDialog).toHaveBeenCalled()
  })

  it('toggles an inactive flow by sending an active status', async () => {
    mocks.getApprovalFlows.mockResolvedValue([inactiveFlow])
    mocks.updateApprovalFlow.mockResolvedValue({ ...inactiveFlow, is_active: 1 })
    const wrapper = mountPage()
    await vi.waitFor(() => expect(wrapper.text()).toContain('回款审批'))

    await wrapper.get('[data-testid="approval-flow-toggle-12"]').trigger('click')
    await vi.waitFor(() => expect(mocks.updateApprovalFlow).toHaveBeenCalledWith(12, { is_active: 1 }))
  })

  it('reloads the list after the form emits success', async () => {
    const wrapper = mountPage()
    await waitForLoaded(wrapper)
    const initialCalls = mocks.getApprovalFlows.mock.calls.length

    await triggerHeaderAction('create-approval-flow')
    await wrapper.get('[data-testid="approval-flow-form-success"]').trigger('click')
    await flushPromises()

    expect(mocks.getApprovalFlows).toHaveBeenCalledTimes(initialCalls + 1)
  })

  it('handles toggle failure without changing the original status', async () => {
    const failure = new Error('toggle failed')
    mocks.updateApprovalFlow.mockRejectedValue(failure)
    const wrapper = mountPage()
    await waitForLoaded(wrapper)

    await wrapper.get('[data-testid="approval-flow-toggle-11"]').trigger('click')
    await vi.waitFor(() => expect(mocks.handleApiError).toHaveBeenCalledWith(failure, '停用审批流程'))
    expect(wrapper.text()).toContain('启用')
    expect(mocks.getApprovalFlows).toHaveBeenCalledTimes(1)
  })

  it('renders workflow name, draft status, and node count', async () => {
    const wrapper = mountPage()
    await vi.waitFor(() => expect(wrapper.text()).toContain('商机跟进自动化'))

    expect(wrapper.text()).toContain('草稿')
    expect(wrapper.text()).toMatch(/节点数\s*4/)
  })

  it('shows workflow creation only with automation:create permission', async () => {
    const wrapper = mountPage()
    await vi.waitFor(() => expect(wrapper.text()).toContain('商机跟进自动化'))
    expect(headerActionVisible('create-workflow')).toBe(true)

    const permissionStore = usePermissionStore()
    permissionStore.permissions = permissionStore.permissions.filter(permission => permission.code !== 'automation:create')
    await flushPromises()
    expect(headerActionVisible('create-workflow')).toBe(false)
  })

  it('publishes a workflow through updateStatus', async () => {
    const wrapper = mountPage()
    await vi.waitFor(() => expect(wrapper.text()).toContain('商机跟进自动化'))

    await wrapper.get('[data-testid="workflow-publish-21"]').trigger('click')
    await vi.waitFor(() => expect(mocks.updateWorkflowStatus).toHaveBeenCalledWith(21, { status: 'published' }))
  })
  it('pauses a published workflow through updateStatus', async () => {
    mocks.listWorkflows.mockResolvedValue([publishedWorkflow])
    const wrapper = mountPage()
    await vi.waitFor(() => expect(wrapper.text()).toContain('已发布自动化'))

    await wrapper.get('[data-testid="workflow-pause-23"]').trigger('click')
    await vi.waitFor(() => expect(mocks.updateWorkflowStatus).toHaveBeenCalledWith(23, { status: 'paused' }))
  })
  it('resumes a paused workflow through updateStatus', async () => {
    mocks.listWorkflows.mockResolvedValue([pausedWorkflow])
    const wrapper = mountPage()
    await vi.waitFor(() => expect(wrapper.text()).toContain('暂停自动化'))

    await wrapper.get('[data-testid="workflow-resume-22"]').trigger('click')
    await vi.waitFor(() => expect(mocks.updateWorkflowStatus).toHaveBeenCalledWith(22, { status: 'published' }))
  })

  it('opens the workflow editor and reloads after save', async () => {
    const wrapper = mountPage()
    await vi.waitFor(() => expect(wrapper.text()).toContain('商机跟进自动化'))
    const initialCalls = mocks.listWorkflows.mock.calls.length

    await wrapper.get('[data-testid="workflow-edit-21"]').trigger('click')
    expect(wrapper.get('[data-testid="workflow-editor-id"]').text()).toBe('21')
    await wrapper.get('[data-testid="workflow-editor-save"]').trigger('click')
    await flushPromises()
    expect(mocks.listWorkflows).toHaveBeenCalledTimes(initialCalls + 1)
  })

  it('does not request workflow data without automation read permission', async () => {
    const wrapper = mountPage(['approval:flow:view'])
    await vi.waitFor(() => expect(mocks.getApprovalFlows).toHaveBeenCalled())

    expect(mocks.listWorkflows).not.toHaveBeenCalled()
    expect(wrapper.find('[aria-label="工作流列表"]').exists()).toBe(false)
  })
  it('does not request legacy approval data without approval read permission', async () => {
    const wrapper = mountPage(['automation:read', 'automation:create'])
    await vi.waitFor(() => expect(mocks.listWorkflows).toHaveBeenCalled())

    expect(mocks.getApprovalFlows).not.toHaveBeenCalled()
    expect(wrapper.find('[aria-label="工作流列表"]').exists()).toBe(true)
  })
})
