import { describe, expect, it } from 'vitest'
import { buildResetValues } from '../filterPanelValues'

const fields = [
  { key: 'keyword' },
  { key: 'status' },
  { key: 'due_date' }
]

describe('buildResetValues', () => {
  it('resets text, select, and date filter values to empty strings', () => {
    expect(buildResetValues(fields, {
      keyword: '客户',
      status: 'PENDING',
      due_date: '2026-07-14'
    })).toEqual({
      keyword: '',
      status: '',
      due_date: ''
    })
  })

  it('preserves controlled caller keys while resetting them safely', () => {
    expect(buildResetValues(fields, {
      keyword: '客户',
      external_filter: 2
    })).toEqual({
      keyword: '',
      status: '',
      due_date: '',
      external_filter: ''
    })
  })
})
