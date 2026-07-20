import axios, { AxiosError, type AxiosRequestConfig } from 'axios'
import { useUserStore } from '@/stores/user'

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL

const axiosInstance = axios.create({
  baseURL: apiBaseUrl === undefined || apiBaseUrl === null || apiBaseUrl.trim() === '' ? '/api' : apiBaseUrl,
  timeout: 30000, // 普通请求超时 30 秒（AI SSE 不使用 axios）
})

axiosInstance.interceptors.request.use(
  (config) => {
    const userStore = useUserStore()
    const token = userStore.token
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
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
    return data
  },
  (error: AxiosError) => {
    // 只处理 401（跳转登录）
    if (error.response?.status === 401) {
      const userStore = useUserStore()
      userStore.logout()
      window.location.href = '/login'
    }

    // 所有其他错误由页面级处理（使用 handleApiError）
    // 这样可以让页面根据具体业务场景提供更清晰的错误提示

    return Promise.reject(error)
  }
)

interface RequestInstance {
  get<T = unknown>(url: string, config?: AxiosRequestConfig): Promise<T>
  post<T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T>
  put<T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T>
  delete<T = unknown>(url: string, config?: AxiosRequestConfig): Promise<T>
  patch<T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T>
}

const request: RequestInstance = {
  get: (url, config) => axiosInstance.get(url, config),
  post: (url, data, config) => axiosInstance.post(url, data, config),
  put: (url, data, config) => axiosInstance.put(url, data, config),
  delete: (url, config) => axiosInstance.delete(url, config),
  patch: (url, data, config) => axiosInstance.patch(url, data, config)
}

export default request
