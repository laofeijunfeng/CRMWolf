import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import DeploymentInfoFormDialog from '@/components/dialogs/DeploymentInfoFormDialog.vue'

vi.mock('@/api/deployment', () => ({
  default: { create: vi.fn() },
}))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))

const passthrough = (name: string) => defineComponent({ name, template: '<div><slot /></div>' })

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
  template: '<input :id="id" :value="modelValue" />',
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
  Switch: passthrough('Switch'),
}

describe('DeploymentInfoFormDialog', () => {
  it('does not request opening when mounted closed', async () => {
    const wrapper = mount(DeploymentInfoFormDialog, {
      props: { open: false, customerId: 'customer-1' },
      global: { stubs },
    })

    await wrapper.vm.$nextTick()

    expect(wrapper.emitted('update:open')).toBeUndefined()
  })
})
