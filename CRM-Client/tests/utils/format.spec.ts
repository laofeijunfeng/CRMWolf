/**
 * Task C3: 通用格式化工具单测（C-DSG-7 条10）
 *
 * 覆盖 formatCurrency（Intl zh-CN CNY）+ formatDateRelative（<24h 相对、否则绝对）。
 * 非法入参优雅回退。时间断言用 vi.useFakeTimers 固定"现在"。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { formatCurrency, formatDateRelative } from '@/utils/format'

describe('formatCurrency', () => {
  it('formats a positive number as CNY currency', () => {
    expect(formatCurrency(58000)).toBe('¥58,000.00')
    expect(formatCurrency(120000)).toBe('¥120,000.00')
  })

  it('formats a fractional number with 2 decimals', () => {
    expect(formatCurrency(1234.5)).toBe('¥1,234.50')
  })

  it('accepts numeric string input', () => {
    expect(formatCurrency('9800.25')).toBe('¥9,800.25')
  })

  it('falls back to ¥0.00 for non-finite values', () => {
    expect(formatCurrency(NaN)).toBe('¥0.00')
    expect(formatCurrency(Infinity)).toBe('¥0.00')
    expect(formatCurrency(null)).toBe('¥0.00')
    expect(formatCurrency(undefined)).toBe('¥0.00')
    expect(formatCurrency('')).toBe('¥0.00')
    expect(formatCurrency('not-a-number')).toBe('¥0.00')
  })
})

describe('formatDateRelative', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-07-02T10:00:00'))
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('returns "刚刚" within the same minute', () => {
    expect(formatDateRelative('2026-07-02T09:59:50')).toBe('刚刚')
  })

  it('returns "N 分钟前" within an hour', () => {
    expect(formatDateRelative('2026-07-02T09:42:00')).toBe('18 分钟前')
  })

  it('returns "N 小时前" within 24 hours', () => {
    expect(formatDateRelative('2026-07-01T19:00:00')).toBe('15 小时前')
  })

  it('switches to absolute YYYY-MM-DD HH:mm past 24h', () => {
    expect(formatDateRelative('2026-06-28T08:30:00')).toBe('2026-06-28 08:30')
  })

  it('accepts Date instance', () => {
    expect(formatDateRelative(new Date('2026-07-02T09:00:00'))).toBe('1 小时前')
  })

  it('accepts timestamp in milliseconds', () => {
    // 2026-07-02T08:00:00Z ≈ now - 2h in UTC; relative uses local but is fine
    expect(formatDateRelative(Date.now() - 2 * 3600 * 1000)).toBe('2 小时前')
  })

  it('returns "-" for invalid input', () => {
    expect(formatDateRelative(null)).toBe('-')
    expect(formatDateRelative('')).toBe('-')
    expect(formatDateRelative(undefined)).toBe('-')
    expect(formatDateRelative('not-a-date')).toBe('-')
  })

  it('falls back to absolute for future times (clock skew)', () => {
    expect(formatDateRelative('2026-07-03T10:00:00')).toBe('2026-07-03 10:00')
  })
})