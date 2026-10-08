import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import FailureCard from '@/components/sales-assistant/FailureCard.vue'

describe('customer not found failure card', () => {
  it('offers rename and abort for either not-found wording when the field is customer', () => {
    const wrapper = mount(FailureCard, {
      props: { message: '未找到对应客户，请核对并提供客户准确名称。', waiting: { type: 'FIELD', field: 'customer', question_id: 'q1', prompt: '未找到对应客户' } },
    })

    expect(wrapper.text()).toContain('尚未写入')
    expect(wrapper.text()).toContain('修改客户名称')
    expect(wrapper.text()).toContain('结束本次记录')
  })
})
