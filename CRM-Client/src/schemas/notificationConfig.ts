import { z } from 'zod'
import { BusinessDateTimeStringSchema } from './common'

const NullableString = z.string().nullable()

export const NotificationConfigResponseSchema = z.object({
  id: z.number().int().positive(),
  team_id: z.number().int().positive(),
  notification_method: z.string(),
  feishu_webhook_url: NullableString,
  feishu_webhook_enabled: z.boolean().nullable(),
  notification_group_name: NullableString,
  feishu_app_id: NullableString,
  feishu_app_secret: NullableString,
  feishu_api_enabled: z.boolean().nullable(),
  created_time: BusinessDateTimeStringSchema,
  updated_time: BusinessDateTimeStringSchema
})

export const NotificationTestResponseSchema = z.object({
  success: z.boolean(),
  message: z.string()
})

export type NotificationConfigResponse = z.infer<typeof NotificationConfigResponseSchema>
export type NotificationTestResponse = z.infer<typeof NotificationTestResponseSchema>
