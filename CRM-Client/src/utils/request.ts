import axios, { AxiosError, InternalAxiosRequestConfig, AxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'

interface CustomAxiosRequestConfig extends InternalAxiosRequestConfig {
  skipErrorNotification?: boolean
}

const axiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 30000  // 普通请求超时 30 秒（AI SSE 不使用 axios）
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

axiosInstance.interceptors.response.use(
  (response) => {
    console.log('API 响应:', response.config.url, response.status, response.data)
    return response.data
  },
  (error: AxiosError) => {
    const config = error.config as CustomAxiosRequestConfig
    
    if (!config?.skipErrorNotification) {
      console.error('API 错误:', error.config?.url, error.response?.status, error.response?.data)
      const message = (error.response?.data as any)?.detail || (error.response?.data as any)?.message || error.message || '请求失败'
      ElMessage.error(message)
    }
    
    if (error.response?.status === 401) {
      const userStore = useUserStore()
      userStore.logout()
      window.location.href = '/login'
    }
    
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
