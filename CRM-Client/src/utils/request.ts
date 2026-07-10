import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios'
import { useUserStore } from '@/stores/user'

const axiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
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
    console.log('API 响应:', response.config.url, response.status, response.data)
    return response.data
  },
  (error: AxiosError) => {
    console.error('API 错误:', error.config?.url, error.response?.status, error.response?.data)

    // 只处理 401（跳转登录）
    if (error.response?.status === 401) {
      const userStore = useUserStore()
      userStore.logout()
      window.location.href = '/login'
    }

    // ❌ 移除全局 ElMessage.error()
    // 所有其他错误由页面级处理（使用 handleApiError）
    // 这样可以让页面根据具体业务场景提供更清晰的错误提示

    return Promise.reject(error)
  }
)

interface RequestInstance {
  get<T = any>(url: string, config?: AxiosRequestConfig): Promise<T>
  post<T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T>
  put<T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T>
  delete<T = any>(url: string, config?: AxiosRequestConfig): Promise<T>
  patch<T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T>
}

const request: RequestInstance = {
  get: (url, config) => axiosInstance.get(url, config),
  post: (url, data, config) => axiosInstance.post(url, data, config),
  put: (url, data, config) => axiosInstance.put(url, data, config),
  delete: (url, config) => axiosInstance.delete(url, config),
  patch: (url, data, config) => axiosInstance.patch(url, data, config)
}

export default request
