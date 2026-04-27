/**
 * Store 示例 - 类型安全实现
 *
 * @description 展示如何按照规范实现类型安全的 Pinia Store
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { CustomerResponse, CustomerCreate } from '@/schemas/customer'
import { CustomerListResponseSchema } from '@/schemas/customer'
import { customerApi } from '@/api/customer'
import type { PaginationParams } from '@/schemas/common'

/**
 * 客户 Store 示例
 *
 * @example
 * // 在组件中使用
 * const customerStore = useCustomerStore()
 * const { items, loading, error } = storeToRefs(customerStore)
 * const { fetchList, create } = customerStore
 *
 * // 调用 action
 * await fetchList({ page: 1, pageSize: 20 })
 */
export const useCustomerStore = defineStore('customer', () => {
  // ===== State（必须类型化） =====

  /** 客户列表 */
  const items = ref<CustomerResponse[]>([])

  /** 加载状态 */
  const loading = ref<boolean>(false)

  /** 错误信息 */
  const error = ref<string | null>(null)

  /** 当前选中客户 ID */
  const currentId = ref<number | null>(null)

  /** 总数 */
  const total = ref<number>(0)

  // ===== Computed（必须返回类型） =====

  /** 当前选中的客户 */
  const currentItem = computed<CustomerResponse | null>(() => {
    return items.value.find(item => item.id === currentId.value) ?? null
  })

  /** 是否有数据 */
  const hasItems = computed<boolean>(() => {
    return items.value.length > 0
  })

  /** 是否正在加载 */
  const isLoading = computed<boolean>(() => {
    return loading.value
  })

  // ===== Actions（必须参数和返回类型） =====

  /**
   * 获取客户列表
   *
   * @param params - 分页参数
   */
  const fetchList = async (params: PaginationParams): Promise<void> => {
    loading.value = true
    error.value = null

    try {
      const response = await customerApi.getList(params)
      // Zod 已在 API 层校验，这里直接赋值
      items.value = response.data
      total.value = response.total
    } catch (e) {
      // 类型安全的错误处理
      error.value = e instanceof Error ? e.message : '获取客户列表失败'
    } finally {
      loading.value = false
    }
  }

  /**
   * 获取单个客户详情
   *
   * @param id - 客户 ID
   * @returns 客户详情或 null
   */
  const fetchById = async (id: number): Promise<CustomerResponse | null> => {
    loading.value = true
    error.value = null

    try {
      const customer = await customerApi.getById(id)
      currentId.value = customer.id
      // 更新列表中的客户（如果存在）
      const index = items.value.findIndex(item => item.id === id)
      if (index >= 0) {
        items.value[index] = customer
      }
      return customer
    } catch (e) {
      error.value = e instanceof Error ? e.message : '获取客户详情失败'
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * 创建客户
   *
   * @param data - 创建数据
   * @returns 创建的客户或 null
   */
  const create = async (data: CustomerCreate): Promise<CustomerResponse | null> => {
    loading.value = true
    error.value = null

    try {
      const customer = await customerApi.create(data)
      items.value.push(customer)
      total.value += 1
      return customer
    } catch (e) {
      error.value = e instanceof Error ? e.message : '创建客户失败'
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * 清空状态
   */
  const clear = (): void => {
    items.value = []
    currentId.value = null
    error.value = null
    total.value = 0
    loading.value = false
  }

  // ===== 返回所有导出 =====
  return {
    // State
    items,
    loading,
    error,
    currentId,
    total,
    // Computed
    currentItem,
    hasItems,
    isLoading,
    // Actions
    fetchList,
    fetchById,
    create,
    clear
  }
})

// ===== 错误示例（禁止） =====

/**
 * ❌ 禁止示例 1：State 使用 any
 *
 * // 错误
 * const items = ref<any[]>([])
 *
 * // 正确
 * const items = ref<CustomerResponse[]>([])
 */

/**
 * ❌ 禁止示例 2：Computed 无返回类型
 *
 * // 错误
 * const currentItem = computed(() => {
 *   return items.value.find(...)
 * })
 *
 * // 正确
 * const currentItem = computed<CustomerResponse | null>(() => {
 *   return items.value.find(...) ?? null
 * })
 */

/**
 * ❌ 禁止示例 3：Action 参数无类型
 *
 * // 错误
 * const fetchList = async (params) => { ... }
 *
 * // 正确
 * const fetchList = async (params: PaginationParams): Promise<void> => { ... }
 */

/**
 * ❌ 禁止示例 4：直接解构 State（失去响应性）
 *
 * // 错误
 * const { items } = useCustomerStore()  // 失去响应性
 *
 * // 正确：使用 storeToRefs
 * const { items } = storeToRefs(useCustomerStore())
 */