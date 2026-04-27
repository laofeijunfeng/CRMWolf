/**
 * 测试示例 - 类型安全实现
 *
 * @description 展示如何按照规范编写类型安全的测试
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

// ===== 导入待测试模块 =====
import CustomerCard from '@/components/CustomerCard.example.vue'
import type { CustomerResponse } from '@/schemas/customer'

// ===== Mock 数据（遵循 TYPESCRIPT.md 类型） =====
const mockCustomer: CustomerResponse = {
  id: 1,
  account_name: '测试公司',
  industry: '互联网',
  city: '北京',
  address: '北京市朝阳区',
  company_scale: '51-200',
  source: '线上注册',
  status: '0',
  owner_id: 'ou_test123',
  source_lead_id: null,
  default_procurement_method_id: null,
  return_reason: null,
  returned_time: null,
  creator_id: 'ou_test123',
  created_time: '2024-01-01T00:00:00Z',
  last_modified_time: '2024-01-01T00:00:00Z',
  version: 1
}

// ===== 组件测试 =====
describe('CustomerCard', () => {
  beforeEach(() => {
    // 每个测试前初始化 Pinia
    setActivePinia(createPinia())
  })

  describe('渲染测试', () => {
    it('renders customer name correctly', () => {
      const wrapper = mount(CustomerCard, {
        props: { customer: mockCustomer }
      })

      expect(wrapper.text()).toContain('测试公司')
    })

    it('renders status text correctly', () => {
      const wrapper = mount(CustomerCard, {
        props: { customer: mockCustomer }
      })

      expect(wrapper.text()).toContain('跟进中')
    })

    it('renders city correctly', () => {
      const wrapper = mount(CustomerCard, {
        props: { customer: mockCustomer }
      })

      expect(wrapper.text()).toContain('北京')
    })
  })

  describe('交互测试', () => {
    it('emits update event when save button clicked', async () => {
      const wrapper = mount(CustomerCard, {
        props: { customer: mockCustomer, mode: 'edit' }
      })

      // 触发编辑模式
      await wrapper.find('.wolf-btn-secondary').trigger('click')

      // 触发保存
      await wrapper.find('.wolf-btn-primary').trigger('click')

      expect(wrapper.emitted('update')).toBeTruthy()
    })

    it('emits delete event when delete button clicked', async () => {
      const wrapper = mount(CustomerCard, {
        props: { customer: mockCustomer }
      })

      await wrapper.find('.wolf-btn-danger').trigger('click')

      expect(wrapper.emitted('delete')).toBeTruthy()
      expect(wrapper.emitted('delete')[0]).toEqual([1])
    })
  })

  describe('权限测试', () => {
    it('hides edit button when user lacks permission', () => {
      // Mock 无权限状态
      vi.mock('@/stores/permissions', () => ({
        usePermissionsStore: () => ({
          hasPermission: (code: string) => code !== 'customer:update'
        })
      }))

      const wrapper = mount(CustomerCard, {
        props: { customer: mockCustomer }
      })

      expect(wrapper.find('.wolf-btn-secondary').exists()).toBe(false)
    })

    it('shows edit button when user has permission', () => {
      // Mock 有权限状态
      vi.mock('@/stores/permissions', () => ({
        usePermissionsStore: () => ({
          hasPermission: () => true
        })
      }))

      const wrapper = mount(CustomerCard, {
        props: { customer: mockCustomer }
      })

      expect(wrapper.find('.wolf-btn-secondary').exists()).toBe(true)
    })
  })

  describe('状态测试', () => {
    it('shows loading spinner when loading', () => {
      const wrapper = mount(CustomerCard, {
        props: { customer: mockCustomer },
        global: {
          mocks: {
            $store: {
              loading: true
            }
          }
        }
      })

      expect(wrapper.find('.wolf-loading').exists()).toBe(true)
    })

    it('shows error message when error occurs', () => {
      const wrapper = mount(CustomerCard, {
        props: { customer: mockCustomer },
        global: {
          mocks: {
            $store: {
              error: '加载失败'
            }
          }
        }
      })

      expect(wrapper.find('.wolf-error').text()).toContain('加载失败')
    })
  })
})

// ===== 错误示例（禁止） =====

/**
 * ❌ 禁止示例 1：Mock 数据使用 any
 *
 * // 错误
 * const mockCustomer: any = { ... }
 *
 * // 正确：使用 Approved Types
 * const mockCustomer: CustomerResponse = { ... }
 */

/**
 * ❌ 禁止示例 2：跳过测试
 *
 * // 错误
 * it.skip('some test', () => { ... })
 *
 * // 正确：完成所有测试
 * it('some test', () => { ... })
 */

/**
 * ❌ 禁止示例 3：无边界测试
 *
 * // 错误：只测一个场景
 * it('works', () => {
 *   expect(true).toBe(true)
 * })
 *
 * // 正确：覆盖多种场景
 * describe('渲染测试', () => { ... })
 * describe('交互测试', () => { ... })
 * describe('权限测试', () => { ... })
 * describe('状态测试', () => { ... })
 */

/**
 * ❌ 禁止示例 4：不测试 emit 参数
 *
 * // 错误
 * expect(wrapper.emitted('delete')).toBeTruthy()
 *
 * // 正确：验证 emit 参数
 * expect(wrapper.emitted('delete')[0]).toEqual([mockCustomer.id])
 */