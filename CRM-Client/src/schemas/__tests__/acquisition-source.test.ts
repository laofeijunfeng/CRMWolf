import { describe, expect, it } from 'vitest'
import { customerCreateSchema, customerFormSchema } from '../customer-form'
import { leadSchema } from '../lead-form'
import { getAcquisitionSourceDisplayName } from '../acquisition-source'

describe('acquisition source form schemas', () => {
  it('requires source_public_id and rejects the old 线索转化 enum', () => {
    const customerResult = customerFormSchema.safeParse({
      account_name: '示例客户',
      city: '北京',
      company_scale: '1-50人',
      source: '线索转化',
      default_procurement_method_id: 1,
    })
    const createResult = customerCreateSchema.safeParse({
      account_name: '示例客户',
      city: '北京',
      company_scale: '1-50人',
      source: '线索转化',
      default_procurement_method_id: 1,
      contact_name: '张三',
      contact_mobile: '13800138000',
      contact_position: '经理',
      contact_gender: '男',
    })
    const leadResult = leadSchema.safeParse({
      lead_name: '示例线索',
      source: '线上注册',
      city: '上海',
      contact_name: '李四',
      contact_phone: '13900139000',
    })

    expect(customerResult.success).toBe(false)
    expect(createResult.success).toBe(false)
    expect(leadResult.success).toBe(false)
  })

  it('accepts source_public_id for customer and lead forms', () => {
    const customerResult = customerFormSchema.safeParse({
      account_name: '示例客户',
      city: '北京',
      company_scale: '1-50人',
      source_public_id: 'acq_referral',
      default_procurement_method_id: 1,
    })
    const leadResult = leadSchema.safeParse({
      lead_name: '示例线索',
      source_public_id: 'acq_website',
      city: '上海',
      contact_name: '李四',
      contact_phone: '13900139000',
    })

    expect(customerResult.success).toBe(true)
    expect(leadResult.success).toBe(true)
  })

  it('follows the current configured name and falls back to 未设置', () => {
    expect(getAcquisitionSourceDisplayName({
      source: '线上注册',
      source_info: { name: '朋友介绍' },
    })).toBe('朋友介绍')
    expect(getAcquisitionSourceDisplayName({ source: null, source_info: null })).toBe('未设置')
  })
})
