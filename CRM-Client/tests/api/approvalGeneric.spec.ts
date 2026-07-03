/**
 * Task C1: 通用审批 API 封装测试
 *
 * 验证 approvalGeneric API 函数构造正确的 URL + body，复用既有 request 实例
 * （不硬编码 baseURL），并对响应走 Zod 校验。
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock request 实例：捕获 url / data / method，返回受控响应体。
// 用 vi.hoisted 提升 mock 对象，使其在 vi.mock 工厂被提升后仍可引用。
const { requestMock } = vi.hoisted(() => ({
  requestMock: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn()
  }
}))

vi.mock('@/utils/request', () => ({
  default: requestMock
}))

import approvalGenericApi, {
  submitApproval,
  approveEntity,
  cancelApproval,
  getApprovalDetail,
  bulkApprove
} from '@/api/approvalGeneric'

describe('approvalGeneric API', () => {
  beforeEach(() => {
    requestMock.get.mockReset()
    requestMock.post.mockReset()
    requestMock.put.mockReset()
    requestMock.delete.mockReset()
    requestMock.patch.mockReset()
  })

  describe('submitApproval', () => {
    it('POST /v1/approvals/{type}/{id}/submit with comment body', async () => {
      requestMock.post.mockResolvedValue({ approval_id: 12, status: 'PENDING' })

      const res = await submitApproval('CONTRACT', 100, '请审批')

      expect(requestMock.post).toHaveBeenCalledOnce()
      const [url, body] = requestMock.post.mock.calls[0] as [string, unknown]
      expect(url).toBe('/v1/approvals/CONTRACT/100/submit')
      expect(body).toEqual({ comment: '请审批' })
      expect(res).toEqual({ approval_id: 12, status: 'PENDING' })
    })

    it('omits comment when not provided (undefined body comment)', async () => {
      requestMock.post.mockResolvedValue({ approval_id: 0, status: 'APPROVED' })

      await submitApproval('PAYMENT', 5)

      const [url, body] = requestMock.post.mock.calls[0] as [string, unknown]
      expect(url).toBe('/v1/approvals/PAYMENT/5/submit')
      expect(body).toEqual({})
    })
  })

  describe('approveEntity', () => {
    it('POST /v1/approvals/{type}/{id}/approve with action+comment', async () => {
      requestMock.post.mockResolvedValue({
        id: 1,
        business_type: 'CONTRACT',
        business_id: 100,
        status: 'APPROVED',
        records: []
      })

      await approveEntity('CONTRACT', 100, 'APPROVE', '同意')

      const [url, body] = requestMock.post.mock.calls[0] as [string, unknown]
      expect(url).toBe('/v1/approvals/CONTRACT/100/approve')
      expect(body).toEqual({ action: 'APPROVE', comment: '同意' })
    })

    it('includes updated_time when provided (optimistic lock)', async () => {
      requestMock.post.mockResolvedValue({
        id: 1,
        business_type: 'INVOICE',
        business_id: 7,
        status: 'APPROVED',
        records: []
      })

      await approveEntity('INVOICE', 7, 'APPROVE', 'ok', '2026-07-02T00:00:00')

      const [, body] = requestMock.post.mock.calls[0] as [string, unknown]
      expect(body).toEqual({
        action: 'APPROVE',
        comment: 'ok',
        updated_time: '2026-07-02T00:00:00'
      })
    })
  })

  describe('cancelApproval', () => {
    it('POST /v1/approvals/{type}/{id}/cancel', async () => {
      requestMock.post.mockResolvedValue({ message: '审批已撤回' })

      const res = await cancelApproval('PAYMENT', 33)

      const [url, body] = requestMock.post.mock.calls[0] as [string, unknown]
      expect(url).toBe('/v1/approvals/PAYMENT/33/cancel')
      expect(body).toEqual({})
      expect(res).toEqual({ message: '审批已撤回' })
    })
  })

  describe('getApprovalDetail', () => {
    it('GET /v1/approvals/{type}/{id}/detail', async () => {
      const detail = {
        id: 9,
        business_type: 'INVOICE',
        business_id: 7,
        contract_id: null,
        flow_id: 2,
        flow_name: '发票审批',
        current_node_id: null,
        current_node_name: null,
        status: 'APPROVED',
        submitter_id: 'u1',
        submitter_name: '张三',
        created_time: '2026-07-01T10:00:00',
        updated_time: '2026-07-01T11:00:00',
        flow_is_active: true,
        flow_disabled_warning: null,
        records: [
          {
            id: 1,
            approval_id: 9,
            node_id: 1,
            node_name: '一审',
            approver_id: 'u2',
            approver_name: '李四',
            approver_status: 'active',
            approver_status_display: '在职',
            action: 'APPROVE',
            comment: '通过',
            created_time: '2026-07-01T10:30:00'
          }
        ]
      }
      requestMock.get.mockResolvedValue(detail)

      const res = await getApprovalDetail('INVOICE', 7)

      const [url] = requestMock.get.mock.calls[0] as [string]
      expect(url).toBe('/v1/approvals/INVOICE/7/detail')
      expect(res).toEqual(detail)
    })
  })

  describe('bulkApprove', () => {
    it('POST /v1/approvals/bulk-approve with entity_type/ids/action/comment', async () => {
      requestMock.post.mockResolvedValue({
        success_count: 2,
        failed: [{ id: 3, reason: '审批实例不存在' }]
      })

      const res = await bulkApprove('PAYMENT', [1, 2, 3], 'APPROVE', '批量通过')

      const [url, body] = requestMock.post.mock.calls[0] as [string, unknown]
      expect(url).toBe('/v1/approvals/bulk-approve')
      expect(body).toEqual({
        entity_type: 'PAYMENT',
        ids: [1, 2, 3],
        action: 'APPROVE',
        comment: '批量通过'
      })
      expect(res.success_count).toBe(2)
      expect(res.failed).toHaveLength(1)
    })

    it('includes updated_times map when provided', async () => {
      requestMock.post.mockResolvedValue({ success_count: 1, failed: [] })

      await bulkApprove('CONTRACT', [10], 'APPROVE', 'ok', { '10': '2026-07-02T00:00:00' })

      const [, body] = requestMock.post.mock.calls[0] as [string, unknown]
      expect(body).toMatchObject({
        updated_times: { '10': '2026-07-02T00:00:00' }
      })
    })
  })

  it('default export exposes all functions', () => {
    expect(approvalGenericApi.submitApproval).toBe(submitApproval)
    expect(approvalGenericApi.approveEntity).toBe(approveEntity)
    expect(approvalGenericApi.cancelApproval).toBe(cancelApproval)
    expect(approvalGenericApi.getApprovalDetail).toBe(getApprovalDetail)
    expect(approvalGenericApi.bulkApprove).toBe(bulkApprove)
  })
})
