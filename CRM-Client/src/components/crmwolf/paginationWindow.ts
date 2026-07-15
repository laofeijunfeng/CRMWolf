export type PaginationEntry =
  | { type: 'page'; value: number; key: string }
  | { type: 'ellipsis'; key: string }

export const buildPaginationEntries = (currentPage: number, pageCount: number): PaginationEntry[] => {
  if (pageCount <= 0) return []

  const safeCurrentPage = Math.min(Math.max(currentPage, 1), pageCount)
  if (pageCount <= 7) {
    return Array.from({ length: pageCount }, (_, index) => ({
      type: 'page' as const,
      value: index + 1,
      key: `page-${index + 1}`
    }))
  }

  const visiblePages = new Set<number>([
    1,
    pageCount,
    safeCurrentPage - 1,
    safeCurrentPage,
    safeCurrentPage + 1
  ])
  const sortedPages = [...visiblePages]
    .filter(pageNumber => pageNumber >= 1 && pageNumber <= pageCount)
    .sort((left, right) => left - right)

  const entries: PaginationEntry[] = []
  sortedPages.forEach((pageNumber, index) => {
    const previousPage = sortedPages[index - 1]
    if (previousPage !== undefined && pageNumber - previousPage > 1) {
      entries.push({ type: 'ellipsis', key: `ellipsis-${previousPage}-${pageNumber}` })
    }
    entries.push({ type: 'page', value: pageNumber, key: `page-${pageNumber}` })
  })

  return entries
}
