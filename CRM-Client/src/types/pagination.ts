export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export const normalizePaginatedResponse = <T>(response: T[] | PaginatedResponse<T>): { items: T[]; total: number } => {
  if (Array.isArray(response)) {
    return { items: response, total: response.length }
  }

  return {
    items: response.items ?? [],
    total: response.total ?? response.items?.length ?? 0
  }
}
