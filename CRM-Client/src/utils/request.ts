import axios, { AxiosError, type AxiosRequestConfig } from 'axios'
import { useUserStore } from '@/stores/user'
import { rememberAuthReturnPath } from '@/utils/authRecovery'

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL
let authRedirectInFlight = false

export interface RequestConfig extends AxiosRequestConfig {
  skipErrorNotification?: boolean
  /** Stable identifier for a user initiated write command. */
  operationId?: string
  /** Client generated key used to make a write safe to retry. */
  idempotencyKey?: string
  /** Optimistic concurrency fence understood by command endpoints. */
  expectedVersion?: string | number
  /** Shared trace identifier for the request and its recovery query. */
  correlationId?: string
}

type CommandRequestConfig = Pick<
  RequestConfig,
  'operationId' | 'idempotencyKey' | 'expectedVersion' | 'correlationId'
>

const axiosInstance = axios.create({
  baseURL: apiBaseUrl === undefined || apiBaseUrl === null || apiBaseUrl.trim() === '' ? '/api' : apiBaseUrl,
  timeout: 30000, // 普通请求超时 30 秒（AI SSE 不使用 axios）
})

axiosInstance.interceptors.request.use(
  (config) => {
    const commandConfig = config as typeof config & CommandRequestConfig
    const userStore = useUserStore()
    const token = userStore.token
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    if (commandConfig.operationId !== undefined && commandConfig.operationId !== '') {
      config.headers['X-Operation-Id'] = commandConfig.operationId
    }
    if (commandConfig.idempotencyKey !== undefined && commandConfig.idempotencyKey !== '') {
      config.headers['Idempotency-Key'] = commandConfig.idempotencyKey
    }
    if (commandConfig.expectedVersion !== undefined) {
      config.headers['X-Expected-Version'] = String(commandConfig.expectedVersion)
    }
    if (commandConfig.correlationId !== undefined && commandConfig.correlationId !== '') {
      config.headers['X-Correlation-Id'] = commandConfig.correlationId
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

/**
 * 响应拦截器
 *
 * UI/UX Pro Max §8: error-feedback
 *
 * 职责：
 * - 只处理 401（跳转登录）
 * - 其他错误由页面级处理（使用 handleApiError）
 * - 不再全局显示错误提示，避免重复干扰
 */
axiosInstance.interceptors.response.use(
  (response) => {
    const data: unknown = response.data
    return data as typeof response
  },
  (error: AxiosError) => {
    // 只处理 401（跳转登录）
    if (error.response?.status === 401 && !authRedirectInFlight) {
      authRedirectInFlight = true
      const returnPath = rememberAuthReturnPath()
      const userStore = useUserStore()
      userStore.logout()
      const query = returnPath === null ? '' : `?redirect=${encodeURIComponent(returnPath)}`
      window.location.href = `/login${query}`
    }

    // 所有其他错误由页面级处理（使用 handleApiError）
    // 这样可以让页面根据具体业务场景提供更清晰的错误提示

    return Promise.reject(error)
  }
)

interface RequestInstance {
  get<T = unknown>(url: string, config?: RequestConfig): Promise<T>
  post<T = unknown>(url: string, data?: unknown, config?: RequestConfig): Promise<T>
  put<T = unknown>(url: string, data?: unknown, config?: RequestConfig): Promise<T>
  delete<T = unknown>(url: string, config?: RequestConfig): Promise<T>
  patch<T = unknown>(url: string, data?: unknown, config?: RequestConfig): Promise<T>
}

const request: RequestInstance = {
  get: (url, config) => axiosInstance.get(url, config),
  post: (url, data, config) => axiosInstance.post(url, data, config),
  put: (url, data, config) => axiosInstance.put(url, data, config),
  delete: (url, config) => axiosInstance.delete(url, config),
  patch: (url, data, config) => axiosInstance.patch(url, data, config)
}

export default request
