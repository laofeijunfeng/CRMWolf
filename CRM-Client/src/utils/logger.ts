/**
 * Frontend Logger - 前端日志系统
 *
 * 功能：
 * - 分级日志（debug/info/warn/error）
 * - 批量发送 + 本地缓冲
 * - 发送失败时 localStorage 暌存
 * - 指数退避重试
 * - 与 Vue/Pinia 集成
 * - 支持上下文标签（便于追踪）
 *
 * 使用示例：
 * ```ts
 * import { logger } from '@/utils/logger'
 *
 * logger.debug('[AIAssistant]', 'restore', { stepsCount: 5 })
 * logger.info('[AgentExecutionLog]', 'setStepsDirectly', { success: true })
 * logger.error('[API]', 'fetchFailed', { url: '/api/x', error: 'Network' })
 *
 * // 关键路径追踪
 * logger.trace('execution-restore', [
 *   { step: 'loadConversation', data: { id: 123 } },
 *   { step: 'getExecutionSteps', data: { count: 5 } },
 *   { step: 'setStepsDirectly', data: { success: true } }
 * ])
 * ```
 */

import request from '@/utils/request'
import { DEFAULT_LOGGER_CONFIG, type LoggerConfig } from './logger.config'
import { useUserStore } from '@/stores/user'
import { teamApi } from '@/api/team'
import type { App as VueApp } from 'vue'
import type { Store as PiniaStore } from 'pinia'

// ========== Types ==========

type LogLevel = 'debug' | 'info' | 'warn' | 'error'

interface LogEntry {
  level: LogLevel
  context: string
  action: string
  data: unknown
  timestamp: number
  traceId?: string
  // 新增：用户关联
  userId?: number
  teamId?: number
}

interface TraceStep {
  step: string
  data?: unknown
  timestamp?: number
}

// ========== User Info Getter ==========

/**
 * 获取当前用户信息（userId + teamId）
 *
 * @returns userId 和 teamId（可能为 undefined）
 */
async function getCurrentUserInfo(): Promise<{ userId?: number; teamId?: number }> {
  try {
    const userStore = useUserStore()
    const userId = userStore.userInfo?.id

    // 获取当前团队 ID
    let teamId: number | undefined
    try {
      const teamsResponse = await teamApi.getUserTeams()
      teamId = teamsResponse.current_team_id
    } catch {
      // 获取团队失败时静默忽略
      console.warn('[Logger] Failed to get team info')
    }

    // 返回时显式处理 undefined
    const result: { userId?: number; teamId?: number } = {}
    if (userId !== undefined) {
      result.userId = userId
    }
    if (teamId !== undefined) {
      result.teamId = teamId
    }
    return result
  } catch {
    return {}
  }
}

// 缓存用户信息（避免频繁请求）
let cachedUserInfo: { userId?: number; teamId?: number } | null = null
let userInfoCacheTime = 0
const USER_INFO_CACHE_DURATION = 60000 // 1 分钟缓存

async function getCachedUserInfo(): Promise<{ userId?: number; teamId?: number }> {
  const now = Date.now()
  if (cachedUserInfo && now - userInfoCacheTime < USER_INFO_CACHE_DURATION) {
    return cachedUserInfo
  }

  cachedUserInfo = await getCurrentUserInfo()
  userInfoCacheTime = now
  return cachedUserInfo
}

// ========== Logger Class ==========

class FrontendLogger {
  private config: LoggerConfig
  private buffer: LogEntry[] = []
  private flushTimer: number | null = null
  private retryCount = 0
  private isSending = false
  private sessionId: string

  constructor(config: Partial<LoggerConfig> = {}) {
    this.config = { ...DEFAULT_LOGGER_CONFIG, ...config }
    this.sessionId = this.generateSessionId()

    // 启动定时发送
    this.startFlushTimer()

    // 恢复 localStorage 中暂存的日志
    this.restoreFromStorage()

    // 页面离开时发送剩余日志
    this.setupUnloadHandler()

    // 捕获全局错误
    this.setupErrorHandler()
  }

  // ========== Public Methods ==========

  /**
   * Debug 级别日志（开发调试用）
   */
  debug(context: string, action: string, data: unknown): void {
    this.log('debug', context, action, data)
  }

  /**
   * Info 级别日志（关键操作记录）
   */
  info(context: string, action: string, data: unknown): void {
    this.log('info', context, action, data)
  }

  /**
   * Warn 级别日志（警告信息）
   */
  warn(context: string, action: string, data: unknown): void {
    this.log('warn', context, action, data)
  }

  /**
   * Error 级别日志（错误信息）
   */
  error(context: string, action: string, data: unknown): void {
    this.log('error', context, action, data)
  }

  /**
   * 关键路径追踪（用于复杂流程调试）
   *
   * 示例：
   * ```ts
   * logger.trace('execution-restore', [
   *   { step: 'loadConversation', data: { id: 123 } },
   *   { step: 'getExecutionSteps', data: { count: 5 } },
   *   { step: 'setStepsDirectly', data: { success: true } }
   * ])
   * ```
   */
  trace(traceId: string, steps: TraceStep[]): void {
    const lastStep = steps[steps.length - 1]
    const firstStep = steps[0]
    const traceData = {
      traceId,
      steps: steps.map(s => ({
        ...s,
        timestamp: s.timestamp ?? Date.now()
      })),
      duration: steps.length > 1 && lastStep && firstStep
        ? (lastStep.timestamp ?? Date.now()) - (firstStep.timestamp ?? Date.now())
        : 0
    }

    this.log('info', '[TRACE]', traceId, traceData)
  }

  /**
   * 立即发送所有缓冲日志
   */
  async flush(): Promise<void> {
    if (this.isSending || this.buffer.length === 0) return

    this.stopFlushTimer()
    await this.sendLogs()
    this.startFlushTimer()
  }

  /**
   * 更新配置
   */
  updateConfig(config: Partial<LoggerConfig>): void {
    this.config = { ...this.config, ...config }

    if (this.config.enabled) {
      this.startFlushTimer()
    } else {
      this.stopFlushTimer()
    }
  }

  // ========== Private Methods ==========

  private async log(level: LogLevel, context: string, action: string, data: unknown): Promise<void> {
    // 获取用户信息（异步但不阻塞）
    const userInfo = await getCachedUserInfo()

    const entry: LogEntry = {
      level,
      context,
      action,
      data,
      timestamp: Date.now(),
      traceId: this.sessionId,
      ...(userInfo.userId !== undefined && { userId: userInfo.userId }),
      ...(userInfo.teamId !== undefined && { teamId: userInfo.teamId })
    }

    // Console 输出（开发环境）
    if (this.config.consoleOutput) {
      this.outputToConsole(entry)
    }

    // 加入缓冲
    this.buffer.push(entry)

    // 达到缓冲大小立即发送
    if (this.buffer.length >= this.config.bufferSize) {
      this.flush()
    }
  }

  private outputToConsole(entry: LogEntry): void {
    const prefix = `${entry.context} ${entry.action}`

    switch (entry.level) {
      case 'debug':
        console.debug(prefix, entry.data)
        break
      case 'info':
        console.info(prefix, entry.data)
        break
      case 'warn':
        console.warn(prefix, entry.data)
        break
      case 'error':
        console.error(prefix, entry.data)
        break
    }
  }

  private async sendLogs(): Promise<void> {
    if (!this.config.enabled || this.buffer.length === 0) return

    this.isSending = true
    const logsToSend = [...this.buffer]
    this.buffer = []

    try {
      await request.post(this.config.endpoint, {
        logs: logsToSend,
        sessionId: this.sessionId,
        userAgent: navigator.userAgent,
        url: window.location.href
      })

      // 发送成功，重置重试计数
      this.retryCount = 0

      // 清理 localStorage 暂存
      this.clearStorage()

    } catch (error) {
      // 发送失败，日志重新加回缓冲
      this.buffer.unshift(...logsToSend)

      // 暂存到 localStorage（防止页面关闭丢失）
      this.saveToStorage(logsToSend)

      // 指数退避重试
      this.retryCount++
      if (this.retryCount <= this.config.maxRetries) {
        const delay = Math.min(1000 * Math.pow(2, this.retryCount), 30000)
        setTimeout(() => this.flush(), delay)
      }
    }

    this.isSending = false
  }

  private startFlushTimer(): void {
    if (!this.config.enabled || this.flushTimer) return

    this.flushTimer = window.setInterval(() => {
      this.flush()
    }, this.config.flushInterval)
  }

  private stopFlushTimer(): void {
    if (this.flushTimer) {
      clearInterval(this.flushTimer)
      this.flushTimer = null
    }
  }

  private generateSessionId(): string {
    return `session-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
  }

  // ========== localStorage 暂存 ==========

  private saveToStorage(logs: LogEntry[]): void {
    try {
      const existing = this.getStoredLogs()
      const combined = [...existing, ...logs]

      // 限制最大数量（防止 localStorage 爆炸）
      const maxStored = 100
      const trimmed = combined.slice(-maxStored)

      localStorage.setItem(this.config.storageKey, JSON.stringify(trimmed))
    } catch {
      // localStorage 可能已满，静默忽略
    }
  }

  private getStoredLogs(): LogEntry[] {
    try {
      const stored = localStorage.getItem(this.config.storageKey)
      return stored ? JSON.parse(stored) : []
    } catch {
      return []
    }
  }

  private restoreFromStorage(): void {
    const stored = this.getStoredLogs()
    if (stored.length > 0) {
      this.buffer.unshift(...stored)
      console.info('[Logger] Restored logs from localStorage:', stored.length)
    }
  }

  private clearStorage(): void {
    try {
      localStorage.removeItem(this.config.storageKey)
    } catch {
      // 静默忽略
    }
  }

  // ========== 生命周期处理 ==========

  private setupUnloadHandler(): void {
    // 页面离开时发送剩余日志
    window.addEventListener('beforeunload', () => {
      if (this.buffer.length > 0) {
        // 使用 sendBeacon（可靠发送，不阻塞页面关闭）
        const payload = JSON.stringify({
          logs: this.buffer,
          sessionId: this.sessionId
        })

        navigator.sendBeacon?.(this.config.beaconEndpoint, payload)

        // 兜底：暂存到 localStorage
        this.saveToStorage(this.buffer)
      }
    })

    // 页面隐藏时（移动端切换 app）也发送
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'hidden') {
        this.flush()
      }
    })
  }

  // ========== 全局错误捕获 ==========

  private setupErrorHandler(): void {
    // 捕获未处理的 Promise 错误
    window.addEventListener('unhandledrejection', (event) => {
      this.error('[GLOBAL]', 'unhandledrejection', {
        reason: event.reason,
        promise: String(event.promise)
      })
    })

    // 捕获全局 JS 错误
    window.addEventListener('error', (event) => {
      this.error('[GLOBAL]', 'jsError', {
        message: event.message,
        filename: event.filename,
        lineno: event.lineno,
        colno: event.colno
      })
    })
  }
}

// ========== Singleton Instance ==========

export const logger = new FrontendLogger()

// ========== Vue Plugin（可选） ==========

/**
 * Vue 插件：自动注入 logger 到组件
 *
 * 使用：
 * ```ts
 * // main.ts
 * app.use(LoggerPlugin)
 *
 * // 组件中
 * this.$logger.info('component-action', { ... })
 * ```
 */
export const LoggerPlugin = {
  install(app: VueApp): void {
    // Using bracket notation to avoid index signature issue
    app.config.globalProperties['$logger'] = logger

    // Vue 错误捕获
    app.config.errorHandler = (err: unknown, instance: unknown, info: string) => {
      logger.error('[Vue]', 'errorHandler', {
        error: String(err),
        component: (instance as { $options?: { name?: string } })?.$options?.name || 'unknown',
        info
      })
    }
  }
}

// ========== Pinia Plugin（可选） ==========

/**
 * Pinia 插件：自动记录 store action
 *
 * 使用：
 * ```ts
 * // stores/index.ts
 * const pinia = createPinia()
 * pinia.use(PiniaLoggerPlugin)
 * ```
 */
export const PiniaLoggerPlugin = ({ store }: { store: PiniaStore }): void => {
  // 记录每个 action 调用
  store.$onAction(({ name, args, after, onError }) => {
    logger.debug(`[Store:${store.$id}]`, name, { args })

    after((result: unknown) => {
      logger.debug(`[Store:${store.$id}]`, `${name}:completed`, { result })
    })

    onError((error: unknown) => {
      logger.error(`[Store:${store.$id}]`, `${name}:error`, { error: String(error) })
    })
  })
}

// ========== Type Imports（已在文件顶部导入） ==========