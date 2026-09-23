import request from '@/utils/request'
import { ReminderObjectCatalogSchema, ReminderRecipientSchema, ReminderRuleRunSchema, ReminderRuleSchema, type ReminderCondition, type ReminderObjectCatalog, type ReminderRecipient, type ReminderRule, type ReminderRuleRun } from '@/schemas/reminderRule'

export interface ReminderRuleWrite {
  version?: 2
  name: string
  object_type: ReminderRule['object_type']
  trigger: ReminderRule['trigger']
  status?: string | null
  inactive_days?: number | null
  date_field?: string | null
  offset_days?: number | null
  require_no_new_activity: boolean
  trigger_time?: string | null
  conditions?: ReminderCondition[]
  recipients: string[]
  message_title?: string | null
  message_template: string
  channels: ('in_app' | 'feishu')[]
  notify_once_per_window?: boolean
}

const reminderRuleApi = {
  catalog: async (): Promise<ReminderObjectCatalog[]> => {
    return ReminderObjectCatalogSchema.array().parse(await request.get('/v1/reminder-rules/catalog'))
  },
  recipients: async (): Promise<ReminderRecipient[]> => {
    return ReminderRecipientSchema.array().parse(await request.get('/v1/reminder-rules/recipients'))
  },
  list: async (): Promise<ReminderRule[]> => {
    return ReminderRuleSchema.array().parse(await request.get('/v1/reminder-rules'))
  },
  listRuns: async (): Promise<ReminderRuleRun[]> => {
    return ReminderRuleRunSchema.array().parse(await request.get('/v1/reminder-rules/runs'))
  },
  create: async (data: ReminderRuleWrite): Promise<ReminderRule> => {
    return ReminderRuleSchema.parse(await request.post('/v1/reminder-rules', data))
  },
  update: async (id: number, data: ReminderRuleWrite, expectedRevision: number): Promise<ReminderRule> => {
    return ReminderRuleSchema.parse(await request.put(`/v1/reminder-rules/${id}`, { ...data, expected_revision: expectedRevision }))
  },
  setEnabled: async (id: number, enabled: boolean, expectedRevision: number): Promise<ReminderRule> => {
    return ReminderRuleSchema.parse(await request.put(`/v1/reminder-rules/${id}/enabled`, { enabled, expected_revision: expectedRevision }))
  },
}

export default reminderRuleApi
