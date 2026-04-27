import { type EventType } from '@/api/operationLog'

export type { EventType }

export interface EventTypeInfo {
  label: string
  icon: string
  color: string
  bgColor: string
  description: string
}

export const EVENT_TYPE_CONFIG: Record<EventType, EventTypeInfo> = {
  LEAD_CREATED: {
    label: '创建线索',
    icon: 'icon-plus-circle',
    color: '#1890FF',
    bgColor: '#E6F7FF',
    description: '创建了新线索'
  },
  LEAD_CONVERTED: {
    label: '线索转化',
    icon: 'icon-sync',
    color: '#52C41A',
    bgColor: '#F6FFED',
    description: '将线索转化为客户'
  },
  CUSTOMER_CREATED: {
    label: '创建客户',
    icon: 'icon-user-group',
    color: '#722ED1',
    bgColor: '#F9F0FF',
    description: '创建了新客户'
  },
  MANUAL_FOLLOW_UP: {
    label: '手动跟进',
    icon: 'icon-message',
    color: '#1890FF',
    bgColor: '#E6F7FF',
    description: '添加了跟进记录'
  },
  OPPORTUNITY_CREATED: {
    label: '创建商机',
    icon: 'icon-heart-fill',
    color: '#FA8C16',
    bgColor: '#FFF7E6',
    description: '创建了新商机'
  },
  CONTRACT_CREATED: {
    label: '创建合同',
    icon: 'icon-file',
    color: '#13C2C2',
    bgColor: '#E6FFFB',
    description: '创建了新合同'
  },
  CONTRACT_STATUS_CHANGED: {
    label: '合同状态变更',
    icon: 'icon-check-circle',
    color: '#52C41A',
    bgColor: '#F6FFED',
    description: '合同状态已更新'
  },
  INVOICE_CREATED: {
    label: '创建发票',
    icon: 'icon-file',
    color: '#EB2F96',
    bgColor: '#FFF0F6',
    description: '创建了新发票'
  },
  PAYMENT_RECEIVED: {
    label: '回款到账',
    icon: 'icon-check-circle',
    color: '#52C41A',
    bgColor: '#F6FFED',
    description: '回款已到账'
  },
  SYSTEM_ALERT: {
    label: '系统预警',
    icon: 'icon-exclamation-circle',
    color: '#FAAD14',
    bgColor: '#FFFBE6',
    description: '系统预警信息'
  }
}

export const EVENT_TYPE_OPTIONS = Object.entries(EVENT_TYPE_CONFIG).map(([value, config]) => ({
  value,
  label: config.label,
  color: config.color
}))
