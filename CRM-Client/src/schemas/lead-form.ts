import { z } from 'zod'

export const leadSchema = z.object({
  lead_name: z.string()
    .min(2, '线索名称至少 2 个字符')
    .max(100, '线索名称最多 100 个字符'),

  source: z.enum([
    '线上注册', '市场活动', '客户推荐',
    '电话营销', '网站咨询', '展会', '其他'
  ], {
    required_error: '请选择线索来源'
  }),

  city: z.string()
    .min(2, '城市名称至少 2 个字符')
    .max(50, '城市名称最多 50 个字符'),

  company_scale: z.enum([
    '1-50人', '51-200人', '201-500人',
    '501-1000人', '1000人以上'
  ]).optional(),

  contact_name: z.string()
    .min(2, '联系人姓名至少 2 个字符')
    .max(50, '联系人姓名最多 50 个字符'),

  contact_phone: z.string()
    .regex(/^1[3-9]\d{9}$/, '请输入正确的手机号码'),

  remark: z.string()
    .max(500, '备注最多 500 个字符')
    .optional()
})

export type LeadForm = z.infer<typeof leadSchema>