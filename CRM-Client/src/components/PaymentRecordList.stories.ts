import PaymentRecordList from './PaymentRecordList.vue'
import type { PaymentRecordInfo } from '@/api/payment'

interface StoryArgs {
  records: PaymentRecordInfo[]
  canRegister?: boolean
}

interface StoryMeta {
  title: string
  component: typeof PaymentRecordList
  tags: string[]
}

const meta: StoryMeta = {
  title: 'Payment/PaymentRecordList',
  component: PaymentRecordList,
  tags: ['autodocs']
}

export default meta

interface Story {
  args: StoryArgs
}

const records: PaymentRecordInfo[] = [
  {
    id: 501,
    actual_amount: 12345.67,
    payment_date: '2026-07-10',
    creator_name: '张三',
    notes: '首笔到账',
    confirmation_status: 'PENDING',
    created_time: '2026-07-10T09:30:00.000Z',
    approval_id: 9001,
    invoice_application_count: 2
  },
  {
    id: 502,
    actual_amount: 88000,
    payment_date: '2026-07-12',
    creator_name: '李四',
    confirmation_status: 'CONFIRMED',
    created_time: '2026-07-12T10:00:00.000Z',
    invoice_application_count: 0
  }
]

export const Default: Story = {
  args: {
    records,
    canRegister: true
  }
}

export const Empty: Story = {
  args: {
    records: [],
    canRegister: true
  }
}
