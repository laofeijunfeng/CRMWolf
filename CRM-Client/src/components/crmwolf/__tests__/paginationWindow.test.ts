import { describe, expect, it } from 'vitest'
import { buildPaginationEntries } from '../paginationWindow'

const labels = (currentPage: number, pageCount: number): string[] =>
  buildPaginationEntries(currentPage, pageCount).map(entry =>
    entry.type === 'page' ? String(entry.value) : '…'
  )

describe('buildPaginationEntries', () => {
  it('shows every page when the page count is small', () => {
    expect(labels(1, 5)).toEqual(['1', '2', '3', '4', '5'])
  })

  it('windows a large page count at the first page', () => {
    expect(labels(1, 20)).toEqual(['1', '2', '…', '20'])
  })

  it('windows a large page count around a middle page', () => {
    expect(labels(10, 20)).toEqual(['1', '…', '9', '10', '11', '…', '20'])
  })

  it('windows a large page count at the last page', () => {
    expect(labels(20, 20)).toEqual(['1', '…', '19', '20'])
  })

  it('clamps an out-of-range current page to valid boundaries', () => {
    expect(labels(0, 20)).toEqual(['1', '2', '…', '20'])
    expect(labels(21, 20)).toEqual(['1', '…', '19', '20'])
  })

  it('returns no entries when there are no pages', () => {
    expect(buildPaginationEntries(1, 0)).toEqual([])
  })
})
