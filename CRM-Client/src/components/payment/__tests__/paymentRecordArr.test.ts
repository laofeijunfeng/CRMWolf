import { describe, expect, it } from 'vitest'

import { arrCanOpen, arrLinePoints, arrShowsMarker } from '@/components/payment/paymentRecordArr'

describe('payment ARR chart line', () => {
  it('spans an empty month without turning it into zero', () => {
    const points = [
      { ratio: 60 },
      { ratio: 50 },
      { ratio: null },
      { ratio: 0 },
      { ratio: 40 },
    ]

    expect(arrLinePoints(points)).toEqual([
      { ratio: 60 },
      { ratio: 50 },
      { ratio: 0 },
      { ratio: 40 },
    ])
    expect(arrShowsMarker(points)).toBe(false)
    expect(arrCanOpen(null)).toBe(false)
    expect(arrCanOpen(0)).toBe(true)
    expect(arrCanOpen(57)).toBe(true)
  })

  it('keeps an isolated month as a single point', () => {
    const points = [{ ratio: null }, { ratio: 0 }, { ratio: null }]
    expect(arrLinePoints(points)).toEqual([{ ratio: 0 }])
    expect(arrShowsMarker(points)).toBe(true)
  })
})
