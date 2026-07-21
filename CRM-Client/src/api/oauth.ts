import request from '@/utils/request'
import {
  FeishuCallbackResponseSchema,
  InviteLoginOptionsResponseSchema,
  MessageResponseSchema,
  OAuthBindingStatusResponseSchema,
  OAuthLoginUrlResponseSchema,
  OAuthProviderConfigResponseSchema,
  type FeishuCallbackResponse,
  type InviteLoginOptionsResponse,
  type OAuthBindingStatusResponse,
  type OAuthLoginUrlResponse,
  type OAuthProviderConfigResponse,
  type OAuthProviderConfigUpdate,
} from '@/schemas/oauth'

export type {
  FeishuCallbackResponse,
  InviteLoginOptionsResponse,
  OAuthBindingStatusResponse,
  OAuthLoginUrlResponse,
  OAuthProviderConfigResponse,
  OAuthProviderConfigUpdate,
} from '@/schemas/oauth'

export const oauthApi = {
  async getInviteOptions(code: string): Promise<InviteLoginOptionsResponse> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const raw: unknown = await request.get(`/v1/invites/${encodeURIComponent(code)}`)
    return InviteLoginOptionsResponseSchema.parse(raw)
  },

  async getFeishuConfig(): Promise<OAuthProviderConfigResponse> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const raw: unknown = await request.get('/v1/oauth/configs/feishu')
    return OAuthProviderConfigResponseSchema.parse(raw)
  },

  async updateFeishuConfig(data: OAuthProviderConfigUpdate): Promise<OAuthProviderConfigResponse> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const raw: unknown = await request.put('/v1/oauth/configs/feishu', data)
    return OAuthProviderConfigResponseSchema.parse(raw)
  },

  async getFeishuLoginUrl(inviteCode: string): Promise<OAuthLoginUrlResponse> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const raw: unknown = await request.get('/v1/auth/feishu/login-url', {
      params: { invite_code: inviteCode }
    })
    return OAuthLoginUrlResponseSchema.parse(raw)
  },

  async getFeishuBindUrl(): Promise<OAuthLoginUrlResponse> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const raw: unknown = await request.get('/v1/auth/feishu/bind-url')
    return OAuthLoginUrlResponseSchema.parse(raw)
  },

  async handleFeishuCallback(code: string, state: string): Promise<FeishuCallbackResponse> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const raw: unknown = await request.post('/v1/auth/feishu/callback', { code, state })
    return FeishuCallbackResponseSchema.parse(raw)
  },

  async getFeishuBindingStatus(): Promise<OAuthBindingStatusResponse> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const raw: unknown = await request.get('/v1/auth/oauth/feishu/status')
    return OAuthBindingStatusResponseSchema.parse(raw)
  },

  async unbindFeishu(): Promise<{ message: string }> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const raw: unknown = await request.delete('/v1/auth/oauth/feishu/bind')
    return MessageResponseSchema.parse(raw)
  }
}
