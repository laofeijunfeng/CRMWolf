import { z } from 'zod'

export const ReminderConditionSchema = z.object({
  field: z.string(),
  operator: z.string(),
  value: z.unknown().optional(),
})
export const ReminderCatalogChoiceSchema = z.object({ value: z.string(), label: z.string() })
export const ReminderCatalogFieldSchema = ReminderCatalogChoiceSchema.extend({
  operators: z.array(ReminderCatalogChoiceSchema),
  options: z.array(ReminderCatalogChoiceSchema).nullish(),
})
export const ReminderObjectCatalogSchema = z.object({
  object_type: z.enum(['business_journey', 'opportunity', 'customer', 'lead', 'follow_up_task', 'approval', 'payment_plan']),
  label: z.string(),
  recipients: z.array(ReminderCatalogChoiceSchema),
  fields: z.array(ReminderCatalogFieldSchema),
})
export const ReminderRecipientSchema = z.object({ id: z.string(), name: z.string() })


export const ReminderRuleSchema = z.object({
  id: z.number(),
  name: z.string(),
  object_type: z.enum(['business_journey', 'opportunity', 'customer', 'lead', 'follow_up_task', 'approval', 'payment_plan']),
  version: z.number().default(1),
  trigger: z.enum(['schedule', 'change', 'date']),
  status: z.string().nullable().optional(),
  inactive_days: z.number().nullable().optional(),
  date_field: z.string().nullable().optional(),
  offset_days: z.number().nullable().optional(),
  require_no_new_activity: z.boolean().default(false),
  trigger_time: z.string().nullable().optional(),
  conditions: z.array(ReminderConditionSchema).default([]),
  recipients: z.array(z.string()),
  message_title: z.string().nullable().optional(),
  message_template: z.string(),
  channels: z.array(z.string()),
  notify_once_per_window: z.boolean().default(true),
  enabled: z.boolean(),
  revision: z.number().int().positive(),
  sentence: z.string(),
  created_time: z.string(),
  last_modified_time: z.string(),
})

export const ReminderRuleRunSchema = z.object({
  id: z.number(),
  rule_id: z.number(),
  object_type: z.string(),
  object_id: z.number(),
  message: z.string(),
  sent_count: z.number(),
  skipped_count: z.number(),
  created_time: z.string(),
})

export type ReminderCondition = z.infer<typeof ReminderConditionSchema>
export type ReminderObjectCatalog = z.infer<typeof ReminderObjectCatalogSchema>
export type ReminderRule = z.infer<typeof ReminderRuleSchema>
export type ReminderRuleRun = z.infer<typeof ReminderRuleRunSchema>
export type ReminderRecipient = z.infer<typeof ReminderRecipientSchema>
