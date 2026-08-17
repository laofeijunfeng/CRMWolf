import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import SelectField from '@/components/crmwolf/SelectField.vue'

const SelectStub = defineComponent({
  name: 'Select',
  props: {
    modelValue: { type: String, default: '' },
  },
  emits: ['update:modelValue'],
  template: '<div><slot /></div>',
})

const PassthroughStub = defineComponent({
  name: 'PassthroughStub',
  template: '<div><slot /></div>',
})

const SelectItemStub = defineComponent({
  name: 'SelectItem',
  props: {
    value: { type: String, required: true },
  },
  template: '<div><slot /></div>',
})

describe('SelectField', () => {
  it('renders a bottom add action and emits add without changing the selected value', async () => {
    const wrapper = mount(SelectField, {
      props: {
        modelValue: 'production',
        options: [{ value: 'production', label: '生产环境' }],
        addActionLabel: '新增部署信息',
      },
      global: {
        stubs: {
          Select: SelectStub,
          SelectContent: PassthroughStub,
          SelectItem: SelectItemStub,
          SelectSeparator: PassthroughStub,
          SelectTrigger: PassthroughStub,
          SelectValue: PassthroughStub,
          Label: PassthroughStub,
        },
      },
    })

    const options = wrapper.findAllComponents(SelectItemStub)
    expect(options).toHaveLength(2)

    const addAction = options[1]
    expect(addAction?.attributes('aria-label')).toBe('新增部署信息')
    expect(addAction?.find('svg').exists()).toBe(true)
    expect(addAction?.find('.sr-only').text()).toBe('新增部署信息')

    const addActionValue = addAction?.props('value')
    await wrapper.getComponent(SelectStub).vm.$emit('update:modelValue', addActionValue)

    expect(wrapper.emitted('add')).toHaveLength(1)
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  })
})
