/**
 * API 层示例 - 类型安全实现
 *
 * @description 展示如何按照规范实现类型安全的 API 调用
 */

import request from '@/utils/request'
import {
  CustomerListResponseSchema,
  CustomerDetailResponseSchema,
  CustomerResponseSchema,
  type CustomerResponse,
  type CustomerCreate,
  type CustomerUpdate,
  type PaginatedResponse
} from '@/schemas/customer'
import { PaginationParamsSchema, type PaginationParams } from '@/schemas/common'

/**
 * 客户 API
 *
 * @example
 * // 正确用法
 * const result = await customerApi.getList({ page: 1, pageSize: 20 })
 * // result.data 是 CustomerResponse[] 类型
 *
 * // 错误用法（禁止）
 * const result = await customerApi.getList() as any  // ❌ 禁止
 */
export const customerApi = {
  /**
   * 获取客户列表
   *
   * @param params - 分页参数
   * @returns 分页响应，包含 CustomerResponse 数组
   */
  async getList(params: PaginationParams): Promise<PaginatedResponse<CustomerResponse>> {
    // 1. 校验请求参数
    const validatedParams = PaginationParamsSchema.parse(params)

    // 2. 发起请求
    const raw = await request.get('/v1/customers', {
      params: validatedParams
    })

    // 3. Zod 校验响应（边界校验）
    return CustomerListResponseSchema.parse(raw)
  },

  /**
   * 获取客户详情
   *
   * @param id - 客户 ID
   * @returns CustomerDetailResponse
   */
  async getById(id: number): Promise<CustomerResponse> {
    if (id <= 0) {
      throw new Error('Invalid customer ID')
    }

    const raw = await request.get(`/v1/customers/${id}`)
    return CustomerDetailResponseSchema.parse(raw)
  },

  /**
   * 创建客户
   *
   * @param data - 创建数据
   * @returns 创建的客户
   */
  async create(data: CustomerCreate): Promise<CustomerResponse> {
    // Zod 校验请求数据
    const validatedData = CustomerCreateSchema.parse(data)

    const raw = await request.post('/v1/customers', validatedData)
    return CustomerResponseSchema.parse(raw)
  },

  /**
   * 更新客户
   *
   * @param id - 客户 ID
   * @param data - 更新数据
   * @returns 更新后的客户
   */
  async update(id: number, data: CustomerUpdate): Promise<CustomerResponse> {
    const validatedData = CustomerUpdateSchema.parse(data)

    const raw = await request.put(`/v1/customers/${id}`, validatedData)
    return CustomerResponseSchema.parse(raw)
  },

  /**
   * 删除客户
   *
   * @param id - 客户 ID
   */
  async delete(id: number): Promise<void> {
    await request.delete(`/v1/customers/${id}`)
  }
}

// ===== 错误示例（禁止） =====

/**
 * ❌ 禁止示例 1：使用 as any
 *
 * // 错误
 * const result = await request.get('/v1/customers') as any
 *
 * // 正确：使用 Zod 校验
 * const result = CustomerListResponseSchema.parse(await request.get('/v1/customers'))
 */

/**
 * ❌ 禁止示例 2：使用 : any 参数
 *
 * // 错误
 * async getList(params: any) { ... }
 *
 * // 正确：使用 PaginationParams 类型
 * async getList(params: PaginationParams): Promise<...> { ... }
 */

/**
 * ❌ 禁止示例 3：返回 any
 *
 * // 错误
 * async getById(id: number): any { ... }
 *
 * // 正确：返回具体类型
 * async getById(id: number): Promise<CustomerResponse> { ... }
 */