import request from '@/utils/request'
import { z } from 'zod'
import {
  DeploymentInfoSchema,
  type DeploymentInfo,
  type DeploymentInfoCreate,
  type DeploymentInfoUpdate
} from '@/schemas/deployment'

export type DeploymentInfoResponse = DeploymentInfo

const DeploymentInfoListSchema = z.array(DeploymentInfoSchema)

const deploymentApi = {
  // 创建部署信息
  async create(data: DeploymentInfoCreate): Promise<DeploymentInfoResponse> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response = await request.post<DeploymentInfoResponse>('/v1/deployment-infos/', data)
    return DeploymentInfoSchema.parse(response)
  },

  // 获取部署信息列表（别名）
  async list(customerId: string): Promise<DeploymentInfoResponse[]> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response = await request.get<DeploymentInfoResponse[]>('/v1/deployment-infos/', {
      params: { customer_id: customerId }
    })
    return DeploymentInfoListSchema.parse(response)
  },

  // 原方法名（向后兼容）
  async createDeployment(data: DeploymentInfoCreate): Promise<DeploymentInfoResponse> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response = await request.post<DeploymentInfoResponse>('/v1/deployment-infos/', data)
    return DeploymentInfoSchema.parse(response)
  },

  async getDeployments(customerId: string): Promise<DeploymentInfoResponse[]> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response = await request.get<DeploymentInfoResponse[]>('/v1/deployment-infos/', {
      params: { customer_id: customerId }
    })
    return DeploymentInfoListSchema.parse(response)
  },

  async getDeployment(deploymentId: number): Promise<DeploymentInfoResponse> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response = await request.get<DeploymentInfoResponse>(`/v1/deployment-infos/${deploymentId}`)
    return DeploymentInfoSchema.parse(response)
  },

  async updateDeployment(deploymentId: number, data: DeploymentInfoUpdate): Promise<DeploymentInfoResponse> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response = await request.put<DeploymentInfoResponse>(`/v1/deployment-infos/${deploymentId}`, data)
    return DeploymentInfoSchema.parse(response)
  },

  async deleteDeployment(deploymentId: number): Promise<unknown> {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response = await request.delete<unknown>(`/v1/deployment-infos/${deploymentId}`)
    return z.unknown().parse(response)
  },

  async setDefaultDeployment(deploymentId: number, customerId: string): Promise<DeploymentInfoResponse> {
    const response = await request.patch<DeploymentInfoResponse>(
      `/v1/deployment-infos/${deploymentId}/set-default`,
      null,
      { params: { customer_id: customerId } }
    )
    return DeploymentInfoSchema.parse(response)
  }
}

export default deploymentApi
