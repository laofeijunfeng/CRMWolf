/**
 * Task C1: 通用审批 Pinia Store 测试
 *
 * 验证 store action 调对应 API 并将响应走 Zod 校验后落入 currentApprovalDetail
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia, storeToRefs } from 'pinia'

// Mock approvalGeneric API 模块。用 vi.hoisted 提升 mock 对象，
// 使其在 vi.mock 工厂被提升后仍可引用。
const { api } = vi.hoisted(() => ({
  api: {
    submitApproval: vi.fn(),
    approveEntity: vi.fn(),
    cancelApproval: vi.fn(),
    getApprovalDetail: vi.fn(),
    bulkApprove: vi.fn()
  }
}))

vi.mock('@/api/approvalGeneric', () => ({
  default: api,
  submitApproval: api.submitApproval,
  approveEntity: api.approveEntity,
  cancelApproval: api.cancelApproval,
  getApprovalDetail: api.getApprovalDetail,
  bulkApprove: api.bulkApprove
}))

import { useApprovalStore } from '@/stores/approval'
import type { ApprovalDetail } from '@/schemas/approvalGeneric'

const validDetail: ApprovalDetail = {
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

describe('useApprovalStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    api.submitApproval.mockReset()
    api.approveEntity.mockReset()
    api.cancelApproval.mockReset()
    api.getApprovalDetail.mockReset()
    api.bulkApprove.mockReset()
  })

  describe('fetchDetail', () => {
    it('calls getApprovalDetail and stores Zod-validated detail in currentApprovalDetail', async () => {
      api.getApprovalDetail.mockResolvedValue(validDetail)

      const store = useApprovalStore()
      const { currentApprovalDetail } = storeToRefs(store)

      expect(currentApprovalDetail.value).toBeNull()

      const res = await store.fetchDetail('INVOICE', 7)

      expect(api.getApprovalDetail).toHaveBeenCalledWith('INVOICE', 7)
      expect(currentApprovalDetail.value).toEqual(validDetail)
      expect(res).toEqual(validDetail)
    })

    it('rejects malformed response via Zod (bad status enum)', async () => {
      api.getApprovalDetail.mockResolvedValue({
        ...validDetail,
        status: 'NOT_A_STATUS'
      })

      const store = useApprovalStore()
      const { currentApprovalDetail } = storeToRefs(store)

      await expect(store.fetchDetail('INVOICE', 7)).rejects.toThrow()
      expect(currentApprovalDetail.value).toBeNull()
    })

    it('rejects malformed records timeline (missing required id)', async () => {
      api.getApprovalDetail.mockResolvedValue({
        ...validDetail,
        records: [{ approval_id: 9, action: 'APPROVE' }]
      })

      const store = useApprovalStore()
      await expect(store.fetchDetail('INVOICE', 7)).rejects.toThrow()
    })
  })

  describe('submitEntity', () => {
    it('calls submitApproval and returns the submit response', async () => {
      api.submitApproval.mockResolvedValue({ approval_id: 12, status: 'PENDING' })

      const store = useApprovalStore()
      const res = await store.submitEntity('CONTRACT', 100, '请审批')

      expect(api.submitApproval).toHaveBeenCalledWith('CONTRACT', 100, '请审批')
      expect(res.approval_id).toBe(12)
      expect(res.status).toBe('PENDING')
    })

    it('forwards undefined comment', async () => {
      api.submitApproval.mockResolvedValue({ approval_id: 0, status: 'APPROVED' })

      const store = useApprovalStore()
      await store.submitEntity('PAYMENT', 5)

      expect(api.submitApproval).toHaveBeenCalledWith('PAYMENT', 5, undefined)
    })
  })

  describe('approveEntity', () => {
    it('calls approveEntity api and stores Zod-validated returned detail', async () => {
      const approved: ApprovalDetail = { ...validDetail, status: 'APPROVED' }
      api.approveEntity.mockResolvedValue(approved)

      const store = useApprovalStore()
      const { currentApprovalDetail } = storeToRefs(store)

      const res = await store.approveEntity('INVOICE', 7, 'APPROVE', '同意')

      expect(api.approveEntity).toHaveBeenCalledWith('INVOICE', 7, 'APPROVE', '同意', undefined)
      expect(currentApprovalDetail.value).toEqual(approved)
      expect(res).toEqual(approved)
    })

    it('forwards updatedTime optimistic-lock parameter', async () => {
      api.approveEntity.mockResolvedValue({ ...validDetail, status: 'APPROVED' })

      const store = useApprovalStore()
      await store.approveEntity('INVOICE', 7, 'APPROVE', 'ok', '2026-07-02T00:00:00')

      expect(api.approveEntity).toHaveBeenCalledWith(
        'INVOICE', 7, 'APPROVE', 'ok', '2026-07-02T00:00:00'
      )
    })

    it('rejects malformed approve response via Zod', async () => {
      api.approveEntity.mockResolvedValue({
        ...validDetail,
        business_id: 'not-a-number'
      })

      const store = useApprovalStore()
      const { currentApprovalDetail } = storeToRefs(store)

      await expect(store.approveEntity('INVOICE', 7, 'APPROVE', 'ok')).rejects.toThrow()
      expect(currentApprovalDetail.value).toBeNull()
    })
  })

  describe('cancelEntity', () => {
    it('calls cancelApproval and clears currentApprovalDetail', async () => {
      api.cancelApproval.mockResolvedValue({ message: '审批已撤回' })

      const store = useApprovalStore()
      const { currentApprovalDetail } = storeToRefs(store)

      // 先塞一个 detail，再撤回清空
      store.$patch({ currentApprovalDetail: validDetail })
      expect(currentApprovalDetail.value).not.toBeNull()

      const res = await store.cancelEntity('PAYMENT', 33)

      expect(api.cancelApproval).toHaveBeenCalledWith('PAYMENT', 33)
      expect(currentApprovalDetail.value).toBeNull()
      expect(res.message).toBe('审批已撤回')
    })
  })

  describe('bulkApprove', () => {
    it('calls bulkApprove api and returns the summary', async () => {
      api.bulkApprove.mockResolvedValue({
        success_count: 2,
        failed: [{ id: 3, reason: '审批实例不存在' }]
      })

      const store = useApprovalStore()
      const res = await store.bulkApprove('PAYMENT', [1, 2, 3], 'APPROVE', '批量通过')

      expect(api.bulkApprove).toHaveBeenCalledWith('PAYMENT', [1, 2, 3], 'APPROVE', '批量通过', undefined)
      expect(res.success_count).toBe(2)
      expect(res.failed).toHaveLength(1)
    })

    it('rejects malformed bulk response via Zod', async () => {
      api.bulkApprove.mockResolvedValue({
        success_count: 'not-a-number',
        failed: []
      })

      const store = useApprovalStore()
      await expect(store.bulkApprove('PAYMENT', [1], 'APPROVE', 'ok')).rejects.toThrow()
    })
  })

  describe('clearDetail', () => {
    it('resets currentApprovalDetail to null', () => {
      const store = useApprovalStore()
      const { currentApprovalDetail } = storeToRefs(store)

      store.$patch({ currentApprovalDetail: validDetail })
      store.clearDetail()
      expect(currentApprovalDetail.value).toBeNull()
    })
  })
})