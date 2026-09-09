import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import DeploymentInfoFormDialog from '@/components/dialogs/DeploymentInfoFormDialog.vue'

const deploymentApi = vi.hoisted(() => ({
  create: vi.fn(),
}))

vi.mock('@/api/deployment', () => ({
  default: deploymentApi,
}))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))

const passthrough = (name: string) => defineComponent({ name, template: '<div><slot /></div>' })
const SwitchStub = defineComponent({
  name: 'Switch',
  props: {
    modelValue: { type: Boolean, default: false },
    disabled: Boolean,
  },
  emits: ['update:modelValue'],
  template: '<button type="button" :disabled="disabled" @click="$emit(\'update:modelValue\', !modelValue)">切换</button>',
})

const Dialog = defineComponent({
  name: 'Dialog',
  props: { open: Boolean },
  emits: ['update:open'],
  template: '<div v-if="open"><slot /></div>',
})
const AlertDialog = defineComponent({
  name: 'AlertDialog',
  props: { open: Boolean },
  template: '<div v-if="open"><slot /></div>',
})
const InputField = defineComponent({
  name: 'InputField',
  props: {
    modelValue: { type: String, default: '' },
    id: String,
    label: String,
    error: String,
    disabled: Boolean,
  },
  emits: ['update:modelValue'],
  methods: {
    handleInput(event: Event) {
      this.$emit('update:modelValue', (event.target as HTMLInputElement).value)
    },
  },
  template: '<input :id="id" :value="modelValue" @input="handleInput" />',
})

const stubs = {
  Dialog,
  DialogContent: passthrough('DialogContent'),
  DialogDescription: passthrough('DialogDescription'),
  DialogFooter: passthrough('DialogFooter'),
  DialogHeader: passthrough('DialogHeader'),
  DialogTitle: passthrough('DialogTitle'),
  AlertDialog,
  AlertDialogAction: passthrough('AlertDialogAction'),
  AlertDialogCancel: passthrough('AlertDialogCancel'),
  AlertDialogContent: passthrough('AlertDialogContent'),
  AlertDialogDescription: passthrough('AlertDialogDescription'),
  AlertDialogFooter: passthrough('AlertDialogFooter'),
  AlertDialogHeader: passthrough('AlertDialogHeader'),
  AlertDialogTitle: passthrough('AlertDialogTitle'),
  Button: passthrough('Button'),
  InputField,
  Label: passthrough('Label'),
  Switch: SwitchStub,
}

describe('DeploymentInfoFormDialog', () => {
  it('persists the default deployment choice in the form state', async () => {
    const wrapper = mount(DeploymentInfoFormDialog, {
      props: { open: true, customerId: 'customer-1' },
      global: { stubs },
    })

    const switchControl = wrapper.getComponent(SwitchStub)
    expect(switchControl.props('modelValue')).toBe(false)

    await switchControl.trigger('click')

    expect(wrapper.getComponent(SwitchStub).props('modelValue')).toBe(true)
  })

  it('submits the selected default deployment flag to the API', async () => {
    deploymentApi.create.mockResolvedValue({
      id: 'deployment-1',
      customer_id: 'customer-1',
      deployment_name: '生产环境',
      server_address: 'https://crm.example.com',
      is_default: true,
    })

    const wrapper = mount(DeploymentInfoFormDialog, {
      props: { open: true, customerId: 'customer-1' },
      global: { stubs },
    })

    await wrapper.get('#deployment-name').setValue('  生产环境  ')
    await wrapper.get('#deployment-server').setValue('  https://crm.example.com  ')
    await wrapper.getComponent(SwitchStub).trigger('click')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(deploymentApi.create).toHaveBeenCalledWith({
      customer_id: 'customer-1',
      deployment_name: '生产环境',
      server_address: 'https://crm.example.com',
      is_default: true,
    })
  })

  it('does not request opening when mounted closed', async () => {
    const wrapper = mount(DeploymentInfoFormDialog, {
      props: { open: false, customerId: 'customer-1' },
      global: { stubs },
    })

    await wrapper.vm.$nextTick()

    expect(wrapper.emitted('update:open')).toBeUndefined()
  })
})
