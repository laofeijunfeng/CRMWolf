import type { AxiosRequestConfig } from 'axios'
import request from '@/utils/request'
import {
  NotificationConfigResponseSchema,
  NotificationTestResponseSchema,
  type NotificationConfigResponse as SchemaNotificationConfigResponse,
  type NotificationTestResponse as SchemaNotificationTestResponse
} from '@/schemas/notificationConfig'

export type NotificationConfigResponse = SchemaNotificationConfigResponse
export type NotificationTestResponse = SchemaNotificationTestResponse

export interface NotificationConfigUpdate {
  notification_method?: string
  feishu_webhook_url?: string
  feishu_webhook_enabled?: boolean
  notification_group_name?: string
  feishu_app_id?: string
  feishu_app_secret?: string
  feishu_api_enabled?: boolean
}

export const notificationConfigApi = {
  /**
   * 获取通知配置
   *
   * 支持通过 config.skipErrorNotification 抑制拦截器的错误 toast，
   * 用于首次访问时后端返回 404（配置不存在）的正常首态场景。
   */
  getConfig: async (config?: AxiosRequestConfig & { skipErrorNotification?: boolean }): Promise<NotificationConfigResponse> =>
    NotificationConfigResponseSchema.parse(await request.get('/v1/system/configs/notification', config)),

  updateConfig: async (data: NotificationConfigUpdate): Promise<NotificationConfigResponse> =>
    NotificationConfigResponseSchema.parse(await request.put('/v1/system/configs/notification', data)),

  testNotification: async (): Promise<NotificationTestResponse> =>
    NotificationTestResponseSchema.parse(await request.post('/v1/system/configs/notification/test'))
}
