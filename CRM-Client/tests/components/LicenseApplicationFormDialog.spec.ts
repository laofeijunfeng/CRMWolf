import { defineComponent, nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import LicenseApplicationFormDialog from '@/components/dialogs/LicenseApplicationFormDialog.vue'
import type { DeploymentInfoResponse } from '@/api/deployment'

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

describe('LicenseApplicationFormDialog', () => {
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
        stubs: {
          Dialog: DialogStub,
          DialogContent: PassthroughStub,
          DialogDescription: PassthroughStub,
          DialogFooter: PassthroughStub,
          DialogHeader: PassthroughStub,
          DialogTitle: PassthroughStub,
          Button: PassthroughStub,
          SelectField: SelectFieldStub,
          DateField: PassthroughStub,
          InputField: PassthroughStub,
          SegmentedChoiceControl: PassthroughStub,
          TextareaField: PassthroughStub,
          SelectionSummary: PassthroughStub,
          DeploymentInfoFormDialog: DeploymentInfoFormDialogStub,
        },
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
})
