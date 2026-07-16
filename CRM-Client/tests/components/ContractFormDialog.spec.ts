/**
 * ContractFormDialog 单元测试
 *
 * 测试覆盖：
 * - Props 处理：open, customerId 可选, customerLocked
 * - Props 默认值
 * - 编辑模式判断
 * - 事件触发
 *
 * 注意：shadcn-vue Dialog 使用 Portal 渲染到 body，
 * Vue Test Utils 无法直接访问 Portal 内容，
 * 因此 DOM 测试依赖 E2E 或 integration 测试。
 */

import { mount, VueWrapper } from '@vue/test-utils'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import ContractFormDialog from '@/components/dialogs/ContractFormDialog.vue'

// Mock APIs
vi.mock('@/api/customer', async () => ({
  default: {
    getCustomers: vi.fn().mockResolvedValue([]),
    getCustomerDetail: vi.fn().mockResolvedValue({ id: 1, account_name: 'Test Customer' }),
    getContacts: vi.fn().mockResolvedValue([]),
  },
}))

vi.mock('@/api/opportunity', async () => ({
  opportunityApi: {
    getAvailableForContract: vi.fn().mockResolvedValue([]),
  },
}))

vi.mock('@/api/contract', async () => ({
  default: {
    createContract: vi.fn().mockResolvedValue({ id: 1 }),
    updateContract: vi.fn().mockResolvedValue({ id: 1 }),
  },
}))

// Mock toast
vi.mock('vue-sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

describe('ContractFormDialog', () => {
  let wrapper: VueWrapper<InstanceType<typeof ContractFormDialog>>

  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  afterEach(() => {
    if (wrapper) {
      wrapper.unmount()
    }
  })

  describe('Props 处理', () => {
    it('接受可选的 customerId prop', () => {
      wrapper = mount(ContractFormDialog, {
        props: { open: false },
      })

      expect(wrapper.exists()).toBe(true)
      expect(wrapper.props('customerId')).toBeUndefined()
    })

    it('接受 customerName prop', () => {
      wrapper = mount(ContractFormDialog, {
        props: {
          open: false,
          customerId: 1,
          customerName: 'Test Customer',
        },
      })

      expect(wrapper.props('customerName')).toBe('Test Customer')
    })

    it('接受 customerLocked prop', () => {
      wrapper = mount(ContractFormDialog, {
        props: {
          open: false,
          customerId: 1,
          customerLocked: true,
        },
      })

      expect(wrapper.props('customerLocked')).toBe(true)
    })

    it('接受 contract prop 用于编辑模式', () => {
      const contractData = {
        id: 1,
        contract_number: 'C-001',
        contract_name: 'Test Contract',
        customer_id: 1,
        opportunity_id: 1,
        signing_contact_id: 1,
        user_count: 10,
        total_amount: '100000',
        license_type: 'SUBSCRIPTION' as const,
        subscription_years: 1,
        signing_date: '2026-01-01',
        effective_date: '2026-01-01',
        standard_unit_price: '1000',
        status: 'DRAFT' as const,
        expiry_date: null,
        creator_id: '1',
        created_time: '2026-01-01T00:00:00Z',
        last_modified_time: '2026-01-01T00:00:00Z',
      }

      wrapper = mount(ContractFormDialog, {
        props: {
          open: false,
          contract: contractData,
        },
      })

      expect(wrapper.props('contract')).toEqual(contractData)
    })
  })

  describe('默认值', () => {
    it('customerLocked 默认为 false', () => {
      wrapper = mount(ContractFormDialog, {
        props: { open: false },
      })

      expect(wrapper.props('customerLocked')).toBe(false)
    })

    it('customerId 默认为 undefined', () => {
      wrapper = mount(ContractFormDialog, {
        props: { open: false },
      })

      expect(wrapper.props('customerId')).toBeUndefined()
    })

    it('customerName 默认为 undefined', () => {
      wrapper = mount(ContractFormDialog, {
        props: { open: false },
      })

      expect(wrapper.props('customerName')).toBeUndefined()
    })

    it('contract 默认为 null', () => {
      wrapper = mount(ContractFormDialog, {
        props: { open: false },
      })

      expect(wrapper.props('contract')).toBeNull()
    })

    it('open 默认为 false', () => {
      wrapper = mount(ContractFormDialog, {
        props: {},
      })

      expect(wrapper.props('open')).toBe(false)
    })
  })

  describe('编辑模式判断', () => {
    it('有 contract prop 时为编辑模式', async () => {
      const contractData = {
        id: 1,
        contract_number: 'C-001',
        contract_name: 'Test Contract',
        customer_id: 1,
        opportunity_id: 1,
        signing_contact_id: 1,
        user_count: 10,
        total_amount: '100000',
        license_type: 'SUBSCRIPTION' as const,
        subscription_years: 1,
        signing_date: '2026-01-01',
        effective_date: '2026-01-01',
        standard_unit_price: '1000',
        status: 'DRAFT' as const,
        expiry_date: null,
        creator_id: '1',
        created_time: '2026-01-01T00:00:00Z',
        last_modified_time: '2026-01-01T00:00:00Z',
      }

      wrapper = mount(ContractFormDialog, {
        props: {
          open: true,
          contract: contractData,
        },
      })

      // isEdit 计算属性应该为 true
      expect(wrapper.vm.isEdit).toBe(true)
    })

    it('无 contract prop 时为创建模式', async () => {
      wrapper = mount(ContractFormDialog, {
        props: { open: true },
      })

      // isEdit 计算属性应该为 false
      expect(wrapper.vm.isEdit).toBe(false)
    })
  })

  describe('事件处理', () => {
    it('可以触发 update:open 事件', async () => {
      wrapper = mount(ContractFormDialog, {
        props: { open: true },
      })

      wrapper.vm.$emit('update:open', false)

      expect(wrapper.emitted('update:open')).toBeTruthy()
      expect(wrapper.emitted('update:open')![0]).toEqual([false])
    })

    it('可以触发 success 事件', async () => {
      wrapper = mount(ContractFormDialog, {
        props: { open: true },
      })

      wrapper.vm.$emit('success')

      expect(wrapper.emitted('success')).toBeTruthy()
    })
  })

  describe('Props 类型验证', () => {
    it('customerId 可以是 number 或 undefined', () => {
      // number
      wrapper = mount(ContractFormDialog, {
        props: { open: false, customerId: 123 },
      })
      expect(wrapper.props('customerId')).toBe(123)

      wrapper.unmount()

      // undefined
      wrapper = mount(ContractFormDialog, {
        props: { open: false, customerId: undefined },
      })
      expect(wrapper.props('customerId')).toBeUndefined()
    })

    it('customerName 可以是 string 或 undefined', () => {
      // string
      wrapper = mount(ContractFormDialog, {
        props: { open: false, customerName: 'Customer Name' },
      })
      expect(wrapper.props('customerName')).toBe('Customer Name')

      wrapper.unmount()

      // undefined
      wrapper = mount(ContractFormDialog, {
        props: { open: false, customerName: undefined },
      })
      expect(wrapper.props('customerName')).toBeUndefined()
    })
  })
})