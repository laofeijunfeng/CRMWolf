/**
 * Logger Configuration
 *
 * Default settings for frontend logging system
 */

export interface LoggerConfig {
  /** 是否启用远程日志（默认：生产环境启用） */
  enabled: boolean
  /** API endpoint */
  endpoint: string
  /** Beacon endpoint (页面关闭时) */
  beaconEndpoint: string
  /** 缓冲区大小（达到此数量立即发送） */
  bufferSize: number
  /** 发送间隔（毫秒） */
  flushInterval: number
  /** 最大重试次数 */
  maxRetries: number
  /** localStorage 键名（用于暂存失败日志） */
  storageKey: string
  /** 是否在 console 显示 */
  consoleOutput: boolean
}

export const DEFAULT_LOGGER_CONFIG: LoggerConfig = {
  enabled: import.meta.env.PROD,
  endpoint: '/v1/logs/batch',
  beaconEndpoint: '/v1/logs/beacon',
  bufferSize: 20,
  flushInterval: 5000,
  maxRetries: 3,
  storageKey: 'crm_frontend_logs',
  consoleOutput: import.meta.env.DEV
}