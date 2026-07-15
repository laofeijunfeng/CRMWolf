import { describe, expect, it } from 'vitest'
import {
  buildResetValues,
  syncFilterValues
} from '../filterPanelValues'

const fields = [
  { key: 'keyword' },
  { key: 'status' },
  { key: 'due_date' }
]

describe('FilterPanel value reducers', () => {
  it('fills missing field keys with empty strings', () => {
    expect(syncFilterValues(fields, { status: 'PENDING' })).toEqual({
      keyword: '',
      status: 'PENDING',
      due_date: ''
    })
  })

  it('resets field and currently controlled extra keys to empty strings', () => {
    expect(buildResetValues(fields, {
      keyword: '客户',
      status: 'PENDING',
      external_filter: 2
    })).toEqual({
      keyword: '',
      status: '',
      due_date: '',
      external_filter: ''
    })
  })
})
