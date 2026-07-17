/**
 * 统一 API 错误处理工具
 * UI/UX Pro Max §8: error-clarity + error-recovery
 *
 * 职责：
 * - 统一处理 API 错误
 * - 根据错误类型提供清晰的原因和修复建议
 * - 符合 UI/UX Pro Max 规范
 */

import { toast } from 'vue-sonner'
import type { AxiosError } from 'axios'

/**
 * 错误类型枚举
 */
export enum ApiErrorType {
  NETWORK = 'network',
  SERVER = 'server',
  AUTH = 'auth',
  BUSINESS = 'business',
  UNKNOWN = 'unknown',
}

/**
 * API 错误信息接口
 */
export interface ApiErrorInfo {
  type: ApiErrorType
  title: string
  description: string
}

/**
 * Axios 响应数据接口
 */
interface AxiosResponseData {
  detail?: string
  message?: string
}

/**
 * 分析错误类型
 */
function analyzeError(error: unknown): ApiErrorInfo {
  // 默认错误信息
  const defaultError: ApiErrorInfo = {
    type: ApiErrorType.UNKNOWN,
    title: '操作失败',
    description: '请稍后重试',
  }

  if (!(error instanceof Error)) {
    return defaultError
  }

  const errorMsg = error.message.toLowerCase()

  // 检查是否为 ZodError（数据验证错误）
  // 使用多种方式检测：name 属性、errors 属性、原型链
  const isZodError =
    error.name === 'ZodError' ||
    'errors' in error ||
    (error.constructor?.name === 'ZodError') ||
    errorMsg.includes('zoderror') ||
    errorMsg.includes('validation')

  if (isZodError) {
    // 打印详细的 Zod 错误信息以便调试
    console.error('ZodError 详情:', error)
    return {
      type: ApiErrorType.UNKNOWN,
      title: '数据格式错误',
      description: '服务器返回的数据格式异常，请联系技术支持',
    }
  }

  // 检查是否为 Axios 错误（需要有 response 或 config 属性）
  const isAxiosError = 'response' in error || 'config' in error
  if (!isAxiosError) {
    return {
      ...defaultError,
      description: errorMsg || defaultError.description,
    }
  }

  const axiosError = error as AxiosError<AxiosResponseData>
  const status = axiosError.response?.status

  // 网络错误（无响应）
  if (!axiosError.response) {
    return {
      type: ApiErrorType.NETWORK,
      title: '网络连接失败',
      description: '网络不稳定或服务器无响应，请检查网络后重试',
    }
  }

  // 网络错误（错误消息包含关键词）
  if (
    errorMsg.includes('network') ||
    errorMsg.includes('fetch') ||
    errorMsg.includes('timeout') ||
    errorMsg.includes('err_network')
  ) {
    return {
      type: ApiErrorType.NETWORK,
      title: '网络连接失败',
      description: '网络不稳定或服务器无响应，请检查网络后重试',
    }
  }

  // 服务器错误 (5xx)
  if (status && status >= 500) {
    return {
      type: ApiErrorType.SERVER,
      title: '服务器错误',
      description: '服务器暂时无法处理请求，请稍后重试',
    }
  }

  // 认证错误 (401)
  if (status === 401) {
    return {
      type: ApiErrorType.AUTH,
      title: '登录已过期',
      description: '请重新登录',
    }
  }

  // 业务错误 (400/422) - 通常有具体的错误信息
  if (status === 400 || status === 422) {
    const detail = axiosError.response?.data?.detail || axiosError.response?.data?.message
    return {
      type: ApiErrorType.BUSINESS,
      title: '操作失败',
      description: detail || errorMsg || '请检查输入后重试',
    }
  }

  // 其他错误
  return {
    ...defaultError,
    description: errorMsg || defaultError.description,
  }
}

/**
 * 统一 API 错误处理函数
 *
 * @param error - 错误对象
 * @param context - 操作上下文（如"登录"、"注册"）
 * @param customMessages - 自定义错误消息（根据错误消息关键词匹配）
 *
 * @example
 * // 基本用法
 * catch (error) {
 *   handleApiError(error, '登录')
 * }
 *
 * @example
 * // 自定义错误消息
 * catch (error) {
 *   handleApiError(error, '登录', {
 *     'password': { title: '密码错误', description: '请检查密码或尝试重置' },
 *     'email': { title: '邮箱未注册', description: '请检查邮箱或切换注册' },
 *   })
 * }
 */
export function handleApiError(
  error: unknown,
  context?: string,
  customMessages?: Record<string, { title: string; description: string }>
): void {
  // 1. 先检查自定义错误消息
  if (error instanceof Error && customMessages) {
    const errorMsg = error.message.toLowerCase()

    for (const [keyword, message] of Object.entries(customMessages)) {
      if (errorMsg.includes(keyword.toLowerCase())) {
        // UI/UX Pro Max §8: toast-accessibility
        // vue-sonner 默认使用 aria-live="polite"，符合无障碍要求
        toast.error(message.title, {
          description: message.description,
          // 自动 4 秒消失，符合 §8 toast-dismiss
        })
        return
      }
    }
  }

  // 2. 分析错误类型
  const errorInfo = analyzeError(error)

  // 3. 添加上下文信息
  let title = errorInfo.title
  if (context && errorInfo.type === ApiErrorType.BUSINESS) {
    title = `${context}失败`
  }

  // 4. 显示错误提示
  // UI/UX Pro Max §8: toast-accessibility
  // vue-sonner 默认使用 aria-live="polite"，符合无障碍要求
  toast.error(title, {
    description: errorInfo.description,
    // 自动 4 秒消失，符合 §8 toast-dismiss
  })
}

/**
 * 网络错误专用处理
 * 用于快速处理网络错误，不需要传入 error 对象
 */
export function handleNetworkError(): void {
  toast.error('网络连接失败', {
    description: '网络不稳定或服务器无响应，请检查网络后重试',
  })
}

/**
 * 服务器错误专用处理
 */
export function handleServerError(): void {
  toast.error('服务器错误', {
    description: '服务器暂时无法处理请求，请稍后重试',
  })
}