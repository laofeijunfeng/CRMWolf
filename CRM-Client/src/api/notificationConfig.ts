/**
 * 通知配置 API
 */
import request from '@/utils/request'

export interface NotificationConfigResponse {
  id: number
  team_id: number
  notification_method: string
  feishu_webhook_url: string | null
  feishu_webhook_enabled: boolean | null
  notification_group_name: string | null
  created_time: string
  updated_time: string
}

export interface NotificationConfigUpdate {
  notification_method?: string
  feishu_webhook_url?: string
  feishu_webhook_enabled?: boolean
  notification_group_name?: string
}

export interface NotificationTestResponse {
  success: boolean
  message: string
}

export const notificationConfigApi = {
  /**
   * 获取通知配置
   */
  getConfig: () => {
    return request.get<{ data: NotificationConfigResponse | null }>('/v1/system/configs/notification')
  },

  /**
   * 更新通知配置
   */
  updateConfig: (data: NotificationConfigUpdate) => {
    return request.put<{ data: NotificationConfigResponse }>('/v1/system/configs/notification', data)
  },

  /**
   * 测试通知发送
   */
  testNotification: () => {
    return request.post<NotificationTestResponse>('/v1/system/configs/notification/test')
  }
}