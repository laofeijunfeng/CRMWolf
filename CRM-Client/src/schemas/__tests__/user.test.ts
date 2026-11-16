import { describe, expect, it } from 'vitest'
import { UserListResponseSchema, UserSearchResultsSchema } from '../user'

const user = {
  id: 1,
  name: 'Sales Operations',
  email: 'sales!ops@example.com',
  mobile: null,
  avatar_url: null,
  employee_no: null,
  region: null,
  status: 'active',
  created_at: '2026-11-13T10:00:00',
  updated_at: '2026-11-13T10:00:00'
}

describe('user response email compatibility', () => {
  it('preserves backend-valid special local parts in lists and search results', () => {
    expect(UserListResponseSchema.parse([{ ...user, roles: [] }])).toEqual([{ ...user, roles: [] }])
    expect(UserSearchResultsSchema.parse([user])).toEqual([user])
    expect(UserSearchResultsSchema.safeParse([{ ...user, email: 123 }]).success).toBe(false)
  })
})
