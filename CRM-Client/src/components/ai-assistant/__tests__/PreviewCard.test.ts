/**
 * PreviewCard.vue 单元测试
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import PreviewCard from '../PreviewCard.vue'

describe('PreviewCard', () => {
  it('renders create_customer action correctly', () => {
    const wrapper = mount(PreviewCard, {
      props: {
        actionType: 'create_customer',
        params: {
          name: '张三公司',
          phone: '13812345678',
          email: 'test@example.com'
        }
      }
    })

    expect(wrapper.find('.preview-card__title').text()).toContain('创建客户')
    expect(wrapper.find('.preview-card__tag').text()).toBe('低风险')
  })

  it('renders win_opportunity with medium risk', () => {
    const wrapper = mount(PreviewCard, {
      props: {
        actionType: 'win_opportunity',
        params: {
          opportunity_name: '大单商机',
          amount: 500000
        }
      }
    })

    expect(wrapper.find('.preview-card__tag').text()).toBe('中风险')
    expect(wrapper.find('.preview-card__tag').classes()).toContain('preview-card__tag--warning')
  })

  it('renders delete_customer with high risk', () => {
    const wrapper = mount(PreviewCard, {
      props: {
        actionType: 'delete_customer',
        params: {
          customer_name: '测试客户',
          reason: '数据错误'
        }
      }
    })

    expect(wrapper.find('.preview-card__tag').text()).toBe('高风险')
    expect(wrapper.find('.preview-card__tag').classes()).toContain('preview-card__tag--danger')
  })

  it('emits confirm event when button clicked', async () => {
    const wrapper = mount(PreviewCard, {
      props: {
        actionType: 'create_customer',
        params: {
          name: '张三公司'
        }
      }
    })

    await wrapper.find('.preview-card__btn--confirm').trigger('click')

    expect(wrapper.emitted('confirm')).toBeTruthy()
    expect(wrapper.emitted('confirm')?.[0]).toEqual(['create_customer', { name: '张三公司' }])
  })

  it('emits cancel event when button clicked', async () => {
    const wrapper = mount(PreviewCard, {
      props: {
        actionType: 'create_customer',
        params: {
          name: '张三公司'
        }
      }
    })

    await wrapper.find('.preview-card__btn--cancel').trigger('click')

    expect(wrapper.emitted('cancel')).toBeTruthy()
  })

  it('disables buttons when loading', () => {
    const wrapper = mount(PreviewCard, {
      props: {
        actionType: 'create_customer',
        params: {
          name: '张三公司'
        },
        loading: true
      }
    })

    expect(wrapper.find('.preview-card__btn--confirm').attributes('disabled')).toBeDefined()
    expect(wrapper.find('.preview-card__btn--cancel').attributes('disabled')).toBeDefined()
    expect(wrapper.find('.preview-card__btn--confirm').text()).toBe('执行中...')
  })

  it('renders multiple fields', () => {
    const wrapper = mount(PreviewCard, {
      props: {
        actionType: 'create_customer',
        params: {
          name: '张三公司',
          phone: '13812345678',
          email: 'test@example.com',
          address: '北京市'
        }
      }
    })

    const fields = wrapper.findAllComponents({ name: 'PreviewField' })
    expect(fields.length).toBeGreaterThan(0)
  })

  it('renders action icon correctly', () => {
    const wrapper = mount(PreviewCard, {
      props: {
        actionType: 'create_customer',
        params: { name: '测试' }
      }
    })

    expect(wrapper.find('.preview-card__icon').text()).toBe('📝')
  })
})