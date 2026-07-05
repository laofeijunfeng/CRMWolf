/**
 * 通用格式化工具（C-DSG-7 条10）
 *
 * - formatCurrency: 金额统一走 Intl.NumberFormat('zh-CN', CNY)，不手拼 ¥ 字符串
 * - formatDateRelative: <24h 相对（"2 小时前"），否则绝对 YYYY-MM-DD HH:mm
 *
 * 纯函数、无副作用、可单测；非数值/非法日期优雅回退原始入参。
 */

/**
 * 金额格式化为人民币（zh-CN，CNY）。
 * 非有限数值（NaN/Infinity）回退为 '¥0.00'。
 */
export const formatCurrency = (value: number | string | null | undefined): string => {
  const num = typeof value === 'string' ? parseFloat(value) : value
  if (num == null || !Number.isFinite(num)) {
    return '¥0.00'
  }
  return new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency: 'CNY',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(num)
}

const pad = (n: number): string => String(n).padStart(2, '0')

/**
 * 格式化日期为 YYYY-MM-DD（本地时区，非 UTC）。
 * 解决 toISOString() 转换 UTC 导致中国时区日期偏移一天的问题。
 * 入参可为 Date 实例；非法入参回退当前日期。
 */
export const formatLocalDate = (date: Date): string => {
  if (date == null || Number.isNaN(date.getTime())) {
    const now = new Date()
    return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
  }
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

/**
 * 获取当前日期 YYYY-MM-DD（本地时区）。
 */
export const getTodayLocalDate = (): string => {
  const now = new Date()
  return formatLocalDate(now)
}

/**
 * 获取 N 天后的日期 YYYY-MM-DD（本地时区）。
 */
export const getDateAfterDays = (days: number): string => {
  const date = new Date()
  date.setDate(date.getDate() + days)
  return formatLocalDate(date)
}

const toAbsolute = (d: Date): string =>
  `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
  `${pad(d.getHours())}:${pad(d.getMinutes())}`

/**
 * 相对时间格式化：<24h 显示「N 分钟前 / N 小时前」，否则 YYYY-MM-DD HH:mm。
 * 入参可为 ISO 字符串、Date 实例或时间戳；非法入参回退 '-'。
 */
export const formatDateRelative = (input: string | number | Date | null | undefined): string => {
  if (input == null || input === '') return '-'
  const d = input instanceof Date ? input : new Date(input)
  if (Number.isNaN(d.getTime())) return '-'

  const now = Date.now()
  const diffMs = now - d.getTime()
  // 未来时间走绝对格式
  if (diffMs < 0) return toAbsolute(d)

  const diffMin = Math.floor(diffMs / 60000)
  if (diffMin < 1) return '刚刚'
  if (diffMin < 60) return `${diffMin} 分钟前`

  const diffHour = Math.floor(diffMin / 60)
  if (diffHour < 24) return `${diffHour} 小时前`

  return toAbsolute(d)
}
