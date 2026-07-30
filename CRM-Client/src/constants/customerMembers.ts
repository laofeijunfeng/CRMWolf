import type { CustomerMemberAccessLevel, CustomerMemberRole } from '@/api/customer'

export const customerMemberRoleOptions: { value: CustomerMemberRole; label: string }[] = [
  { value: 'SALES', label: '销售' },
  { value: 'PRESALES', label: '售前' },
  { value: 'DELIVERY', label: '交付' },
  { value: 'SUPPORT', label: '支持' },
  { value: 'OTHER', label: '其他' },
]

export const customerMemberAccessOptions: { value: CustomerMemberAccessLevel; label: string }[] = [
  { value: 'EDIT', label: '可编辑客户' },
  { value: 'FOLLOW_UP', label: '可跟进' },
  { value: 'VIEW', label: '仅查看' },
]

export const defaultCustomerMemberRole: CustomerMemberRole = 'PRESALES'
export const defaultCustomerMemberAccessLevel: CustomerMemberAccessLevel = 'EDIT'
