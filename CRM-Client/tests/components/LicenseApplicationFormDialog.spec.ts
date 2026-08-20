import { defineComponent, nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import LicenseApplicationFormDialog from '@/components/dialogs/LicenseApplicationFormDialog.vue'
import type { DeploymentInfoResponse } from '@/api/deployment'

const licenseApplicationApi = vi.hoisted(() => ({
  create: vi.fn(),
  submitApplication: vi.fn(),
}))

vi.mock('@/api/licenseApplication', () => ({
  default: licenseApplicationApi,
}))

const DialogStub = defineComponent({
  name: 'Dialog',
  props: {
    open: { type: Boolean, default: false },
  },
  template: '<div v-if="open"><slot /></div>',
})

const PassthroughStub = defineComponent({
  name: 'PassthroughStub',
  template: '<div><slot /></div>',
})

const SelectFieldStub = defineComponent({
  name: 'SelectField',
  props: {
    id: { type: String, default: '' },
    modelValue: { type: [String, Number], default: '' },
    disabled: { type: Boolean, default: false },
    addActionLabel: { type: String, default: '' },
  },
  emits: ['update:modelValue', 'add'],
  template: '<div :data-testid="id" />',
})

const DeploymentInfoFormDialogStub = defineComponent({
  name: 'DeploymentInfoFormDialog',
  props: {
    open: { type: Boolean, default: false },
  },
  emits: ['update:open', 'success'],
  template: '<div data-testid="deployment-info-form-dialog" :data-open="open" />',
})

function findSelectField(wrapper: ReturnType<typeof mount>) {
  const field = wrapper.findAllComponents({ name: 'SelectField' })
    .find((component) => component.props('id') === 'license-deployment')
  if (field === undefined) throw new Error('license deployment field not found')
  return field
}

const DateFieldStub = defineComponent({
  name: 'DateField',
  props: {
    id: { type: String, default: '' },
    modelValue: { type: Date, default: null },
    error: { type: String, default: '' },
  },
  emits: ['update:modelValue'],
  template: '<div :data-testid="id">{{ error }}</div>',
})

const formStubs = {
  Dialog: DialogStub,
  DialogContent: PassthroughStub,
  DialogDescription: PassthroughStub,
  DialogFooter: PassthroughStub,
  DialogHeader: PassthroughStub,
  DialogTitle: PassthroughStub,
  Button: PassthroughStub,
  SelectField: SelectFieldStub,
  DateField: DateFieldStub,
  InputField: PassthroughStub,
  SegmentedChoiceControl: PassthroughStub,
  TextareaField: PassthroughStub,
  SelectionSummary: PassthroughStub,
  DeploymentInfoFormDialog: DeploymentInfoFormDialogStub,
}

const productionDeployment: DeploymentInfoResponse = {
  id: 42,
  customer_id: 'customer-1',
  team_id: 1,
  deployment_name: '生产环境',
  server_address: 'https://crm.example.com',
  authorized_users: 20,
  is_default: false,
  created_time: '2026-08-17T00:00:00',
  last_modified_time: '2026-08-17T00:00:00',
}

describe('LicenseApplicationFormDialog', () => {
  beforeEach(() => {
    licenseApplicationApi.create.mockReset()
    licenseApplicationApi.submitApplication.mockReset()
  })

  it('allows a deployment to be created inline when none exists, then selects it', async () => {
    const wrapper = mount(LicenseApplicationFormDialog, {
      props: {
        open: true,
        customerId: 'customer-1',
        deployments: [],
        contracts: [],
        canCreateDeployment: true,
      },
      global: {
        stubs: formStubs,
      },
    })

    const deploymentField = findSelectField(wrapper)
    expect(deploymentField.props('disabled')).toBe(false)
    expect(deploymentField.props('addActionLabel')).toBe('新增部署信息')

    await deploymentField.vm.$emit('add')
    await nextTick()
    expect(wrapper.getComponent(DeploymentInfoFormDialogStub).props('open')).toBe(true)

    const deployment: DeploymentInfoResponse = {
      id: 42,
      customer_id: 'customer-1',
      team_id: 1,
      deployment_name: '生产环境',
      server_address: 'https://crm.example.com',
      authorized_users: 20,
      is_default: false,
      created_time: '2026-08-17T00:00:00',
      last_modified_time: '2026-08-17T00:00:00',
    }
    await wrapper.getComponent(DeploymentInfoFormDialogStub).vm.$emit('success', deployment)
    await nextTick()

    expect(findSelectField(wrapper).props('modelValue')).toBe('42')
    expect(wrapper.emitted('deployment-created')?.[0]).toEqual([deployment])
  })

  it('rejects expiry dates on local today or earlier without creating an application', async () => {
    const wrapper = mount(LicenseApplicationFormDialog, {
      props: {
        open: true,
        customerId: 'customer-1',
        deployments: [productionDeployment],
        contracts: [],
      },
      global: {
        stubs: formStubs,
      },
    })

    await findSelectField(wrapper).vm.$emit('update:modelValue', '42')
    await nextTick()

    const today = new Date()
    today.setHours(0, 0, 0, 0)
    const dateField = wrapper.getComponent(DateFieldStub)
    await dateField.vm.$emit('update:modelValue', today)
    await wrapper.find('form').trigger('submit')
    await nextTick()

    expect(dateField.text()).toContain('到期日期必须晚于今天')
    expect(licenseApplicationApi.create).not.toHaveBeenCalled()

    const yesterday = new Date(today)
    yesterday.setDate(yesterday.getDate() - 1)
    await dateField.vm.$emit('update:modelValue', yesterday)
    await wrapper.find('form').trigger('submit')
    await nextTick()

    expect(dateField.text()).toContain('到期日期必须晚于今天')
    expect(licenseApplicationApi.create).not.toHaveBeenCalled()
  })
})
