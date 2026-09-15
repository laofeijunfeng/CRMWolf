import { describe, expect, it } from 'vitest'
import { customerCreateSchema, customerEditSchema, customerFormSchema } from '../customer-form'
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

  it('keeps standard scale validation strict while accepting legacy values only for edit', () => {
    const legacyValues = {
      account_name: '示例客户',
      city: '北京',
      company_scale: 'small',
    }
    const profileValues = {
      ...legacyValues,
      source_public_id: 'acq_referral',
      default_procurement_method_id: 1,
    }
    const createValues = {
      ...profileValues,
      contact_name: '张三',
      contact_mobile: '13800138000',
      contact_position: '经理',
      contact_gender: '男',
    }

    expect(customerFormSchema.safeParse(profileValues).success).toBe(false)
    expect(customerCreateSchema.safeParse(createValues).success).toBe(false)
    expect(customerEditSchema.safeParse(legacyValues).success).toBe(true)
  })

  it('accepts optional more-information values on create', () => {
    const result = customerCreateSchema.safeParse({
      account_name: '示例客户',
      city: '上海',
      company_scale: '1-50人',
      source_public_id: 'acq_referral',
      default_procurement_method_id: 1,
      industry: 'internet_saas',
      status: 1,
      license_type: 'TRIAL',
      license_expiry_date: '2026-12-31',
      contact_name: '张三',
      contact_mobile: '13800138000',
      contact_position: '经理',
      contact_gender: '男',
    })
    expect(result.success).toBe(true)
  })

  it('accepts optional more-information values on edit', () => {
    const result = customerEditSchema.safeParse({
      account_name: '示例客户',
      city: '上海',
      company_scale: '1-50人',
      source_public_id: 'acq_referral',
      default_procurement_method_id: 1,
      industry: 'internet_saas',
      status: 1,
      license_type: 'TRIAL',
      license_expiry_date: '2026-12-31',
    })
    expect(result.success).toBe(true)
  })

  it('rejects a non-empty expiry date without a license type on edit', () => {
    const result = customerEditSchema.safeParse({
      account_name: '示例客户',
      city: '上海',
      company_scale: '1-50人',
      source_public_id: 'acq_referral',
      default_procurement_method_id: 1,
      license_expiry_date: '2026-12-31',
    })
    expect(result.success).toBe(false)
  })

  it('rejects a non-empty expiry date without a license type', () => {
    const result = customerCreateSchema.safeParse({
      account_name: '示例客户',
      city: '上海',
      company_scale: '1-50人',
      source_public_id: 'acq_referral',
      default_procurement_method_id: 1,
      license_expiry_date: '2026-12-31',
      contact_name: '张三',
      contact_mobile: '13800139000',
      contact_position: '经理',
      contact_gender: '男',
    })
    expect(result.success).toBe(false)
  })

  it('follows the current configured name and falls back to 未设置', () => {
    expect(getAcquisitionSourceDisplayName({
      source: '线上注册',
      source_info: { name: '朋友介绍' },
    })).toBe('朋友介绍')
    expect(getAcquisitionSourceDisplayName({ source: null, source_info: null })).toBe('未设置')
  })
})
