import { describe, expect, it } from 'vitest'
import {
  getStatusOptions,
  getStatusPresentation,
  type StatusDomain,
} from '../statusPresentation'

describe('status presentation', () => {
  it('keeps approved wording distinct between invoice applications and generic approvals', () => {
    expect(getStatusPresentation('invoiceApplication', 'APPROVED')).toMatchObject({
      label: '已批准',
      tone: 'success',
    })
    expect(getStatusPresentation('approval', 'APPROVED')).toMatchObject({
      label: '已通过',
      tone: 'success',
    })
  })

  it('uses a neutral traceable fallback for unknown values', () => {
    expect(getStatusPresentation('invoiceApplication', 'ARCHIVED')).toEqual({
      label: '未知状态',
      tone: 'neutral',
      traceValue: 'ARCHIVED',
    })
    expect(getStatusPresentation('invoiceApplication', '__proto__')).toEqual({
      label: '未知状态',
      tone: 'neutral',
      traceValue: '__proto__',
    })
  })

  it('keeps invoice filter options aligned with the application mapping', () => {
    expect(getStatusOptions('invoiceApplication')).toEqual([
      { value: 'DRAFT', label: '草稿' },
      { value: 'PENDING_REVIEW', label: '待审批' },
      { value: 'APPROVED', label: '已批准' },
      { value: 'REJECTED', label: '已驳回' },
      { value: 'ISSUED', label: '已开票' },
      { value: 'CANCELLED', label: '已取消' },
    ])
  })

  it('returns unknown status for missing values without throwing', () => {
    const domains: StatusDomain[] = ['approval', 'licenseApplication', 'invoiceApplication']
    for (const domain of domains) {
      expect(getStatusPresentation(domain, undefined)).toMatchObject({
        label: '未知状态',
        tone: 'neutral',
      })
    }
  })
})
