import request from '@/utils/request'

export interface DeploymentInfoCreate {
  customer_id: number
  deployment_name: string
  server_address: string
  authorized_users: number
  is_default?: boolean
}

export interface DeploymentInfoUpdate {
  deployment_name?: string | null
  server_address?: string | null
  authorized_users?: number | null
  is_default?: boolean | null
}

export interface DeploymentInfoResponse {
  id: number
  customer_id: number
  team_id: number
  deployment_name: string
  server_address: string
  authorized_users: number
  is_default: boolean
  created_time: string
  last_modified_time: string
}

const deploymentApi = {
  createDeployment: (data: DeploymentInfoCreate) => {
    return request.post<DeploymentInfoResponse>('/v1/deployment-infos/', data)
  },

  getDeployments: (customerId: number) => {
    return request.get<DeploymentInfoResponse[]>('/v1/deployment-infos/', {
      params: { customer_id: customerId }
    })
  },

  getDeployment: (deploymentId: number) => {
    return request.get<DeploymentInfoResponse>(`/v1/deployment-infos/${deploymentId}`)
  },

  updateDeployment: (deploymentId: number, data: DeploymentInfoUpdate) => {
    return request.put<DeploymentInfoResponse>(`/v1/deployment-infos/${deploymentId}`, data)
  },

  deleteDeployment: (deploymentId: number) => {
    return request.delete<void>(`/v1/deployment-infos/${deploymentId}`)
  },

  setDefaultDeployment: (deploymentId: number, customerId: number) => {
    return request.patch<DeploymentInfoResponse>(
      `/v1/deployment-infos/${deploymentId}/set-default`,
      null,
      { params: { customer_id: customerId } }
    )
  }
}

export default deploymentApi