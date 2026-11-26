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

const Dialog = defineComponent({
  name: 'Dialog',
  props: { open: Boolean },
  emits: ['update:open'],
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
  Button: passthrough('Button'),
  InputField,
}

describe('DeploymentInfoFormDialog', () => {
  it('defaults is_default unchecked and renders a checkbox instead of a switch', async () => {
    deploymentApi.create.mockResolvedValue({
      id: 'deployment-1',
      customer_id: 'customer-1',
      deployment_name: '测试环境',
      server_address: 'https://test.example.com',
      is_default: false,
    })

    const wrapper = mount(DeploymentInfoFormDialog, {
      props: { open: true, customerId: 'customer-1' },
      global: { stubs },
    })

    const checkbox = wrapper.get('#deployment-default[role="checkbox"]')
    expect(checkbox.attributes('aria-checked')).toBe('false')
    expect(wrapper.get('label[for="deployment-default"]').text()).toBe('设为默认部署')
    expect(wrapper.text()).not.toMatch(/[是否]/)

    await wrapper.get('#deployment-name').setValue('测试环境')
    await wrapper.get('#deployment-server').setValue('https://test.example.com')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(deploymentApi.create).toHaveBeenCalledWith({
      customer_id: 'customer-1',
      deployment_name: '测试环境',
      server_address: 'https://test.example.com',
      is_default: false,
    })
  })

  it('submits the checked default deployment flag to the API', async () => {
    deploymentApi.create.mockResolvedValue({
      id: 'deployment-2',
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
    await wrapper.get('#deployment-default[role="checkbox"]').trigger('click')
    expect(wrapper.get('#deployment-default[role="checkbox"]').attributes('aria-checked')).toBe('true')
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
