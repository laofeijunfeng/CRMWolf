import { beforeEach, describe, expect, it, vi } from 'vitest'
import { teamApi } from '@/api/team'

const request = vi.hoisted(() => ({
  get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn(),
}))
vi.mock('@/utils/request', () => ({ default: request }))

const role = { id: 3, name: '销售成员', code: 'SALES_MEMBER' }
const member = {
  id: 8, name: 'Rayson', email: 'rayson@example.com', avatar_url: null,
  current_team: false, joined_at: '2026-01-01T00:00:00Z', roles: [role],
}
const team = {
  id: 7, name: '团队', code: 'TEAM7', owner_id: 1,
  created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
}

describe('teamApi response validation', () => {
  beforeEach(() => vi.resetAllMocks())

  it('accepts numeric member IDs, nullable avatars and preserves current roles', async () => {
    request.get.mockResolvedValue([member])
    expect(await teamApi.getTeamMembers(7)).toEqual([member])
    expect(request.get).toHaveBeenCalledWith('/v1/teams/7/members')
  })

  it('rejects string member IDs instead of letting row actions silently ignore them', async () => {
    request.get.mockResolvedValue([{ ...member, id: '8' }])
    await expect(teamApi.getTeamMembers(7)).rejects.toThrow()
  })

  it('rejects malformed member roles', async () => {
    request.get.mockResolvedValue([{ ...member, roles: [{ ...role, id: '3' }] }])
    await expect(teamApi.getTeamMembers(7)).rejects.toThrow()
  })

  it('validates role assignment acknowledgement and keeps the numeric request contract', async () => {
    const result = { message: '角色已分配', user_id: 8, role_ids: [3] }
    request.post.mockResolvedValue(result)
    expect(await teamApi.assignMemberRoles(7, 8, [3])).toEqual(result)
    expect(request.post).toHaveBeenCalledWith('/v1/teams/7/members/8/roles', { role_ids: [3] })
    request.post.mockResolvedValue({ ...result, role_ids: ['3'] })
    await expect(teamApi.assignMemberRoles(7, 8, [3])).rejects.toThrow()
  })

  it('preserves empty-team responses, nullable current team and numeric owners', async () => {
    request.get.mockResolvedValue({ teams: [], current_team_id: null })
    expect(await teamApi.getUserTeams()).toEqual({ teams: [], current_team_id: null })
    request.get.mockResolvedValue(team)
    expect(await teamApi.getMyTeam()).toEqual(team)
    request.get.mockResolvedValue({ ...team, owner_id: '1' })
    expect(await teamApi.getTeamDetail(7)).toEqual({ ...team, owner_id: '1' })
  })

  it('preserves backend acknowledgement fields without changing request URLs or bodies', async () => {
    const message = { message: '成功', email: 'new@example.com' }
    request.post.mockResolvedValue(team)
    expect(await teamApi.createTeam({ name: '团队' })).toEqual(team)
    expect(request.post).toHaveBeenLastCalledWith('/v1/teams/', { name: '团队' })
    expect(await teamApi.joinTeam({ code: 'TEAM7' })).toEqual(team)
    expect(request.post).toHaveBeenLastCalledWith('/v1/teams/join', { code: 'TEAM7' })
    request.post.mockResolvedValue({ message: '已切换', team_id: 7 })
    expect(await teamApi.switchTeam(7)).toEqual({ message: '已切换', team_id: 7 })
    expect(request.post).toHaveBeenLastCalledWith('/v1/teams/switch', { team_id: 7 })
    request.post.mockResolvedValue(message)
    expect(await teamApi.inviteMember(7, { email: message.email })).toEqual(message)
    expect(request.post).toHaveBeenLastCalledWith('/v1/teams/7/invite', { email: message.email })
    request.post.mockResolvedValue({ message: '已添加', user_id: 8 })
    expect(await teamApi.addMemberDirect(7, 8)).toEqual({ message: '已添加', user_id: 8 })
    expect(request.post).toHaveBeenLastCalledWith('/v1/teams/7/members', { user_id: 8 })
    request.delete.mockResolvedValue({ message: '已移除' })
    expect(await teamApi.removeMember(7, 8)).toEqual({ message: '已移除' })
    expect(request.delete).toHaveBeenCalledWith('/v1/teams/7/members/8')
    request.post.mockResolvedValue({ message: '已重置', code: 'NEW7' })
    expect(await teamApi.regenerateInviteCode(7)).toEqual({ message: '已重置', code: 'NEW7' })
    expect(request.post).toHaveBeenLastCalledWith('/v1/teams/7/regenerate-code')
    request.put.mockResolvedValue(team)
    expect(await teamApi.updateTeam(7, { name: '团队' })).toEqual(team)
    expect(request.put).toHaveBeenLastCalledWith('/v1/teams/7', { name: '团队' })
    request.get.mockResolvedValue([role])
    expect(await teamApi.getMemberRoles(7, 8)).toEqual([role])
    expect(request.get).toHaveBeenLastCalledWith('/v1/teams/7/members/8/roles')
    request.post.mockResolvedValue({ message: '已重置' })
    expect(await teamApi.resetMemberPassword(7, 8, { new_password: 'new-password' })).toEqual({ message: '已重置' })
    expect(request.post).toHaveBeenLastCalledWith('/v1/teams/7/members/8/reset-password', { new_password: 'new-password' })
    const renamed = { message: '已修改', user_id: 8, name: '新名字' }
    request.put.mockResolvedValue(renamed)
    expect(await teamApi.updateMemberName(7, 8, { name: '新名字' })).toEqual(renamed)
    expect(request.put).toHaveBeenLastCalledWith('/v1/teams/7/members/8/name', { name: '新名字' })
  })

  it('propagates request failures unchanged without retrying writes', async () => {
    const error = new Error('forbidden')
    request.post.mockRejectedValue(error)
    await expect(teamApi.assignMemberRoles(7, 8, [3])).rejects.toBe(error)
    expect(request.post).toHaveBeenCalledTimes(1)
  })
})
