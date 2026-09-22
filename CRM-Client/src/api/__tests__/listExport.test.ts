import { describe, expect, it, vi } from 'vitest'

const post = vi.fn()

vi.mock('@/utils/request', () => ({
  default: { post },
}))

const payload = {
  fields: ['account_name'],
  tab: 'all',
  filters: [],
  sorts: [],
}

describe('postListExport', () => {
  it('posts the typed payload as a blob with the export-only zero timeout', async () => {
    post.mockResolvedValue(new Blob(['xlsx']))

    const { postListExport } = await import('../listExport')
    const blob = await postListExport('/v1/customers/export', payload)

    expect(post).toHaveBeenCalledWith('/v1/customers/export', payload, {
      responseType: 'blob',
      timeout: 0,
    })
    expect(blob).toBeInstanceOf(Blob)
  })

  it('wraps non-blob responses into a Blob', async () => {
    post.mockResolvedValue('part-data')

    const { postListExport } = await import('../listExport')
    const blob = await postListExport('/v1/customers/export', payload)

    expect(blob).toBeInstanceOf(Blob)
  })
})
