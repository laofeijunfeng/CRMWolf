import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import AgentUIMessage from '@/components/agent-ui/AgentUIMessage.vue'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { AgentUIEnvelopeSchema } from '@/schemas/agent-contracts'

const message = AgentUIEnvelopeSchema.parse({
  schema_version: 'crm.agent.ui.v1',
  message_id: 8,
  turn_id: 'turn_8',
  role: 'assistant',
  state: 'final',
  blocks: [
    {
      id: 'b_text',
      type: 'text',
      format: 'plain',
      text: '共找到 1 家公司。'
    },
    {
      id: 'b_customers',
      type: 'entity_list',
      entity_type: 'customer',
      result_set_id: 'rs_1',
      total: 1,
      items: [
        {
          entity_ref: {
            ref_id: 'eref_customer_cus_1',
            resource: 'customer',
            public_id: 'cus_1',
            display_name: '上海示例客户',
            result_set_id: 'rs_1'
          }
        }
      ]
    }
  ],
  suggested_actions: [],
  metadata: { route: 'QUERY' }
})

describe('AgentUIMessage', () => {
  it('renders a structured error once', () => {
    const errorMessage = AgentUIEnvelopeSchema.parse({
      ...message,
      message_id: 12,
      turn_id: 'turn_12',
      blocks: [
        {
          id: 'b_error',
          type: 'error',
          code: 'INTERNAL_ERROR',
          title: '处理未完成',
          message: '任务识别服务暂时不可用，请稍后重试。',
          retryable: true,
          trace_id: null,
        },
      ],
    })
    const wrapper = mount(AgentUIMessage, { props: { message: errorMessage } })

    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
    expect(wrapper.text().match(/任务识别服务暂时不可用，请稍后重试。/g)).toHaveLength(1)
  })

  it('renders Workflow progress as a compact collapsible execution process', async () => {
    const workflowMessage = AgentUIEnvelopeSchema.parse({
      ...message,
      message_id: 13,
      turn_id: 'turn_13',
      blocks: [
        { id: 'b_workflow_text', type: 'text', format: 'plain', text: '已创建跟进任务。' },
        {
          id: 'b_process',
          type: 'process',
          title: '执行过程',
          items: [
            { key: 'understand_request', title: '理解业务操作', status: 'COMPLETED' },
            { key: 'prepare_plan', title: '生成执行计划', status: 'COMPLETED' },
            { key: 'execute_action', title: '执行 CRM 操作', status: 'COMPLETED' },
            { key: 'prepare_result', title: '整理执行结果', status: 'COMPLETED' },
          ],
        },
      ],
      metadata: { route: 'WORKFLOW' },
    })
    const wrapper = mount(AgentUIMessage, { props: { message: workflowMessage } })

    expect(wrapper.text()).toContain('已创建跟进任务。')
    expect(wrapper.text()).toContain('整理执行结果')
    expect(wrapper.text()).toContain('4')
    expect(wrapper.text()).not.toContain('理解业务操作')

    await wrapper.get('button').trigger('click')

    expect(wrapper.text()).toContain('理解业务操作')
    expect(wrapper.text()).toContain('生成执行计划')
    expect(wrapper.text()).toContain('执行 CRM 操作')
  })

  it('submits a confirmation with one click and disables the interaction immediately', async () => {
    const confirmationMessage = AgentUIEnvelopeSchema.parse({
      ...message,
      message_id: 14,
      turn_id: 'turn_14',
      blocks: [{
        id: 'b_confirmation',
        type: 'interaction',
        interaction_id: 'int_create_follow_up',
        interaction_type: 'confirmation',
        state: 'ACTIVE',
        prompt: '确认要为「广州凡亚信息科技有限公司」创建跟进任务吗？',
        fields: [],
        options: [
          { value: 'confirm', label: '确认创建', description: null, disabled: false },
          { value: 'cancel', label: '取消', description: null, disabled: false },
        ],
        selection_mode: 'single',
        submit_action_id: 'act_confirm_follow_up',
      }],
      metadata: { route: 'WORKFLOW' },
    })
    const wrapper = mount(AgentUIMessage, { props: { message: confirmationMessage } })
    const confirmButton = wrapper.findAll('button').find(button => button.text() === '确认创建')

    expect(confirmButton).toBeDefined()
    expect(wrapper.findAll('button').some(button => button.text() === '确认')).toBe(false)
    await confirmButton?.trigger('click')
    await confirmButton?.trigger('click')

    expect(wrapper.emitted('interaction')).toEqual([
      ['act_confirm_follow_up', { choice: 'confirm' }],
    ])
    expect(confirmButton?.attributes('disabled')).toBeDefined()
  })

  it('renders follow-up task confirmation as one compact completion control and locks it after completion', async () => {
    const activeMessage = AgentUIEnvelopeSchema.parse({
      ...message,
      message_id: 151,
      turn_id: 'turn_151',
      blocks: [{
        id: 'b_task_confirmation',
        type: 'interaction',
        interaction_id: 'int_task_confirmation',
        interaction_type: 'choice',
        presentation: 'COMPACT_TASK_COMPLETION',
        state: 'ACTIVE',
        prompt: '上次安排的「确认 POC 环境」这次是否已经完成？',
        fields: [],
        options: [
          { value: '已完成', label: '标记完成', description: null, disabled: false },
        ],
        selection_mode: 'single',
        min_selections: 1,
        max_selections: 1,
        submit_on_select: true,
        submit_action_id: 'act_task_confirmation',
      }],
      metadata: { route: 'WORKFLOW' },
    })
    const wrapper = mount(AgentUIMessage, { props: { message: activeMessage } })
    const completeButton = wrapper.get('button[aria-label="标记完成"]')

    expect(wrapper.text()).toContain('上次安排的「确认 POC 环境」这次是否已经完成？')
    expect(wrapper.text()).toContain('待完成')
    expect(wrapper.text()).not.toContain('保持未完成')
    expect(wrapper.text()).not.toContain('不再跟进')
    expect(wrapper.findAll('button')).toHaveLength(1)

    await completeButton.trigger('click')
    await completeButton.trigger('click')

    expect(wrapper.emitted('interaction')).toEqual([
      ['act_task_confirmation', { choice: '已完成' }],
    ])
    expect(completeButton.attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('处理中')

    const completedMessage = AgentUIEnvelopeSchema.parse({
      ...activeMessage,
      blocks: [{
        ...activeMessage.blocks[0],
        state: 'SUBMITTED',
        submit_action_id: null,
      }],
    })
    await wrapper.setProps({ message: completedMessage })

    expect(wrapper.find('button[aria-label="标记完成"]').exists()).toBe(false)
    expect(wrapper.get('[aria-label="已完成"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('已完成')
  })

  it('renders multiple compact task completions as one process-like list', () => {
    const groupedMessage = AgentUIEnvelopeSchema.parse({
      ...message,
      message_id: 152,
      turn_id: 'turn_152',
      blocks: [
        {
          id: 'b_task_1',
          type: 'interaction',
          interaction_id: 'int_task_1',
          interaction_type: 'choice',
          presentation: 'COMPACT_TASK_COMPLETION',
          state: 'ACTIVE',
          prompt: '确认 POC 环境',
          fields: [],
          options: [{ value: '已完成', label: '标记完成', description: null, disabled: false }],
          selection_mode: 'single',
          min_selections: 1,
          max_selections: 1,
          submit_on_select: true,
          submit_action_id: 'act_task_1',
        },
        {
          id: 'b_task_2',
          type: 'interaction',
          interaction_id: 'int_task_2',
          interaction_type: 'choice',
          presentation: 'COMPACT_TASK_COMPLETION',
          state: 'ACTIVE',
          prompt: '确认采购流程',
          fields: [],
          options: [{ value: '已完成', label: '标记完成', description: null, disabled: false }],
          selection_mode: 'single',
          min_selections: 1,
          max_selections: 1,
          submit_on_select: true,
          submit_action_id: 'act_task_2',
        },
      ],
      metadata: { route: 'WORKFLOW' },
    })

    const wrapper = mount(AgentUIMessage, { props: { message: groupedMessage } })
    expect(wrapper.findAll('section[aria-label="待办任务"]')).toHaveLength(1)
    expect(wrapper.findAll('button[aria-label="标记完成"]')).toHaveLength(2)
    expect(wrapper.text()).toContain('确认 POC 环境')
    expect(wrapper.text()).toContain('确认采购流程')
  })

  it('locks form submission immediately and exposes a readable processing state', async () => {
    const textInputMessage = AgentUIEnvelopeSchema.parse({
      ...message,
      message_id: 17,
      turn_id: 'turn_17',
      blocks: [{
        id: 'b_text_input',
        type: 'interaction',
        interaction_id: 'int_text_input',
        interaction_type: 'text_input',
        state: 'ACTIVE',
        prompt: '请补充延期原因',
        fields: [{
          key: 'reason',
          label: '延期原因',
          field_type: 'text',
          required: true,
          default_value: '',
          min_length: 1,
          max_length: 200,
        }],
        options: [],
        selection_mode: null,
        submit_action_id: 'act_text_input',
        allow_blank: false,
      }],
      metadata: { route: 'WORKFLOW' },
    })
    const wrapper = mount(AgentUIMessage, { props: { message: textInputMessage } })

    await wrapper.get('input').setValue('客户要求延期')
    const submitButton = wrapper.findAll('button').find(button => button.text() === '提交')
    await submitButton?.trigger('click')
    await submitButton?.trigger('click')

    expect(wrapper.emitted('interaction')).toEqual([
      ['act_text_input', { text: '客户要求延期' }],
    ])
    expect(wrapper.text()).toContain('处理中')
    expect(submitButton?.attributes('disabled')).toBeDefined()
  })

  it('keeps a submitted confirmation locked until authoritative history is reloaded', async () => {
    const confirmationMessage = AgentUIEnvelopeSchema.parse({
      ...message,
      message_id: 15,
      turn_id: 'turn_15',
      blocks: [{
        id: 'b_confirmation',
        type: 'interaction',
        interaction_id: 'int_create_follow_up',
        interaction_type: 'confirmation',
        state: 'ACTIVE',
        prompt: '确认创建吗？',
        fields: [],
        options: [
          { value: 'confirm', label: '确认创建', description: null, disabled: false },
          { value: 'cancel', label: '取消', description: null, disabled: false },
        ],
        selection_mode: 'single',
        submit_action_id: 'act_confirm_follow_up',
      }],
      metadata: { route: 'WORKFLOW' },
    })
    const wrapper = mount(AgentUIMessage, {
      props: {
        message: confirmationMessage,
        lockedActionIds: new Set<string>(),
      },
    })
    const confirmButton = wrapper.findAll('button').find(button => button.text() === '确认创建')

    await confirmButton?.trigger('click')
    await wrapper.setProps({ disabled: true, lockedActionIds: new Set(['act_confirm_follow_up']) })
    await wrapper.setProps({ disabled: false })

    expect(confirmButton?.attributes('disabled')).toBeDefined()
    await confirmButton?.trigger('click')
    expect(wrapper.emitted('interaction')).toHaveLength(1)

    await wrapper.setProps({ lockedActionIds: new Set<string>() })
    expect(confirmButton?.attributes('disabled')).toBeDefined()
    await confirmButton?.trigger('click')
    expect(wrapper.emitted('interaction')).toHaveLength(1)
  })


  it.each(['SUBMITTED', 'READ_ONLY'] as const)(
    'keeps an authoritative %s confirmation permanently read-only after local locks clear',
    async state => {
      const confirmationMessage = AgentUIEnvelopeSchema.parse({
        ...message,
        message_id: 16,
        turn_id: 'turn_16',
        blocks: [{
          id: 'b_confirmation',
          type: 'interaction',
          interaction_id: 'int_create_follow_up',
          interaction_type: 'confirmation',
          state,
          prompt: '确认创建吗？',
          fields: [],
          options: [
            { value: 'confirm', label: '确认创建', description: null, disabled: false },
            { value: 'cancel', label: '取消', description: null, disabled: false },
          ],
          selection_mode: 'single',
          submit_action_id: null,
        }],
        metadata: { route: 'WORKFLOW' },
      })
      const wrapper = mount(AgentUIMessage, {
        props: {
          message: confirmationMessage,
          lockedActionIds: new Set<string>(),
        },
      })
      const buttons = wrapper.findAll('button')

      expect(buttons).toHaveLength(2)
      expect(buttons.every(button => button.attributes('disabled') !== undefined)).toBe(true)
      await buttons[0]?.trigger('click')
      await buttons[1]?.trigger('click')
      expect(wrapper.emitted('interaction')).toBeUndefined()
    },
  )

  it('renders a compact customer list and keeps local detail navigation available while Agent actions are disabled', async () => {
    const wrapper = mount(AgentUIMessage, { props: { message, disabled: true } })

    expect(wrapper.text()).toContain('共找到 1 家公司。')
    expect(wrapper.text()).toContain('上海示例客户')
    expect(wrapper.findAll('button')).toHaveLength(1)
    expect(wrapper.get('button').attributes('disabled')).toBeUndefined()
    await wrapper.get('button').trigger('click')
    expect(wrapper.emitted('open-entity')).toEqual([[
      {
        ref_id: 'eref_customer_cus_1',
        resource: 'customer',
        public_id: 'cus_1',
        display_name: '上海示例客户',
        result_set_id: 'rs_1'
      }
    ]])
  })

  it('does not present unsupported entity resources as clickable rows', () => {
    const contactMessage = AgentUIEnvelopeSchema.parse({
      ...message,
      message_id: 10,
      turn_id: 'turn_10',
      blocks: [
        {
          id: 'b_contacts',
          type: 'entity_list',
          entity_type: 'contact',
          result_set_id: 'rs_contacts',
          total: 1,
          items: [
            {
              entity_ref: {
                ref_id: 'eref_contact_con_1',
                resource: 'contact',
                public_id: 'con_1',
                display_name: '王总',
                result_set_id: 'rs_contacts'
              }
            }
          ]
        }
      ]
    })
    const wrapper = mount(AgentUIMessage, { props: { message: contactMessage } })

    expect(wrapper.text()).toContain('王总')
    expect(wrapper.findAll('button')).toHaveLength(0)
    expect(wrapper.emitted('open-entity')).toBeUndefined()
  })

  it('keeps interaction controls at the design-system minimum height', () => {
    const interactionMessage = AgentUIEnvelopeSchema.parse({
      ...message,
      message_id: 9,
      turn_id: 'turn_9',
      blocks: [
        {
          id: 'b_note',
          type: 'interaction',
          interaction_id: 'interaction_note',
          interaction_type: 'text_input',
          state: 'ACTIVE',
          prompt: '补充说明',
          fields: [
            {
              key: 'note',
              label: '说明',
              field_type: 'text',
              required: true,
              min_length: 1,
              max_length: 100,
            },
          ],
          options: [],
          allow_blank: false,
          submit_action_id: 'act_submit_note',
        },
      ],
    })
    const wrapper = mount(AgentUIMessage, { props: { message: interactionMessage } })

    expect(wrapper.get('input[type="text"]').classes()).toContain('min-h-11')
    expect(wrapper.get('button').classes()).toContain('min-h-11')
  })

  it('shows field errors, focuses the first invalid field, and preserves values until submission', async () => {
    const validationMessage = AgentUIEnvelopeSchema.parse({
      ...message,
      message_id: 11,
      turn_id: 'turn_11',
      blocks: [
        {
          id: 'b_validation',
          type: 'interaction',
          interaction_id: 'interaction_validation',
          interaction_type: 'form',
          state: 'ACTIVE',
          prompt: '补充客户信息',
          fields: [
            {
              key: 'customer_name',
              label: '客户名称',
              field_type: 'text',
              required: true,
              default_value: '',
              min_length: 3,
              max_length: 100,
            },
            {
              key: 'quantity',
              label: '数量',
              field_type: 'number',
              required: true,
              default_value: null,
              minimum: 1,
              maximum: 10,
            },
          ],
          options: [],
          submit_action_id: 'act_submit_validation',
        },
      ],
    })
    const host = document.createElement('div')
    document.body.appendChild(host)
    const wrapper = mount(AgentUIMessage, {
      attachTo: host,
      props: { message: validationMessage },
    })

    try {
      const submitButton = wrapper.findAll('button').find(button => button.text() === '提交')
      expect(submitButton?.attributes('disabled')).toBeUndefined()
      await submitButton?.trigger('click')

      const nameInput = wrapper.get('#b_validation-customer_name')
      expect(wrapper.text()).toContain('请填写客户名称')
      expect(wrapper.text()).toContain('请填写数量')
      expect(nameInput.attributes('aria-invalid')).toBe('true')
      expect(nameInput.attributes('aria-describedby')).toBe('b_validation-customer_name-error')
      expect(document.activeElement).toBe(nameInput.element)

      const inputs = wrapper.findAllComponents(Input)
      inputs[0]?.vm.$emit('update:modelValue', '上海示例客户')
      inputs[1]?.vm.$emit('update:modelValue', '20')
      await wrapper.vm.$nextTick()
      await submitButton?.trigger('click')

      const quantityInput = wrapper.get('#b_validation-quantity')
      expect(wrapper.text()).toContain('数量不能大于 10')
      expect(document.activeElement).toBe(quantityInput.element)

      inputs[1]?.vm.$emit('update:modelValue', '5')
      await wrapper.vm.$nextTick()
      await submitButton?.trigger('click')

      expect(wrapper.emitted('interaction')).toEqual([
        [
          'act_submit_validation',
          { customer_name: '上海示例客户', quantity: 5 },
        ],
      ])
    } finally {
      wrapper.unmount()
      host.remove()
    }
  })

  it('submits form values through the shared UI controls', async () => {
    const formMessage = AgentUIEnvelopeSchema.parse({
      ...message,
      message_id: 10,
      turn_id: 'turn_10',
      blocks: [
        {
          id: 'b_form',
          type: 'interaction',
          interaction_id: 'interaction_form',
          interaction_type: 'form',
          state: 'ACTIVE',
          prompt: '补充客户信息',
          fields: [
            {
              key: 'summary',
              label: '摘要',
              field_type: 'text',
              required: true,
              default_value: '',
              min_length: 1,
              max_length: 100,
            },
            {
              key: 'detail',
              label: '详情',
              field_type: 'textarea',
              required: true,
              default_value: '',
              min_length: 1,
              max_length: 500,
            },
            {
              key: 'amount',
              label: '金额',
              field_type: 'number',
              required: true,
              default_value: null,
              minimum: 0,
              maximum: 100000,
            },
            {
              key: 'status',
              label: '状态',
              field_type: 'select',
              required: true,
              default_value: null,
              options: [
                { label: '跟进中', value: 'active' },
                { label: '已完成', value: 'done' },
              ],
            },
            {
              key: 'tags',
              label: '标签',
              field_type: 'multi_select',
              required: true,
              default_value: [],
              options: [
                { label: '重点', value: 'important' },
                { label: '续约', value: 'renewal' },
              ],
            },
            {
              key: 'confirmed',
              label: '已确认',
              field_type: 'boolean',
              required: false,
              default_value: false,
            },
          ],
          options: [],
          submit_action_id: 'act_submit_form',
        },
      ],
    })
    const wrapper = mount(AgentUIMessage, { props: { message: formMessage } })

    const inputs = wrapper.findAllComponents(Input)
    expect(inputs).toHaveLength(2)
    expect(wrapper.findComponent(Textarea).exists()).toBe(true)
    expect(wrapper.findAllComponents(Select)).toHaveLength(2)
    expect(wrapper.findComponent(Checkbox).exists()).toBe(true)

    inputs[0]?.vm.$emit('update:modelValue', '年度续约')
    inputs[1]?.vm.$emit('update:modelValue', '12000')
    wrapper.findComponent(Textarea).vm.$emit('update:modelValue', '客户已确认预算')
    const selects = wrapper.findAllComponents(Select)
    selects[0]?.vm.$emit('update:modelValue', 'active')
    selects[1]?.vm.$emit('update:modelValue', ['important', 'renewal'])
    wrapper.findComponent(Checkbox).vm.$emit('update:checked', true)
    await wrapper.vm.$nextTick()

    const submitButton = wrapper.findAll('button').find(button => button.text() === '提交')
    expect(submitButton?.attributes('disabled')).toBeUndefined()
    await submitButton?.trigger('click')
    expect(wrapper.emitted('interaction')).toEqual([
      [
        'act_submit_form',
        {
          summary: '年度续约',
          detail: '客户已确认预算',
          amount: 12000,
          status: 'active',
          tags: ['important', 'renewal'],
          confirmed: true,
        },
      ],
    ])
  })
})
