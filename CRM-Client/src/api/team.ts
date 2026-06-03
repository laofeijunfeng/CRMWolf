import request from '@/utils/request'

export interface RoleSimpleResponse {
  id: number
  name: string
  code: string
}

export interface TeamResponse {
  id: number
  name: string
  code: string
  owner_id: string
  created_at: string
  updated_at?: string
}

export interface TeamCreateRequest {
  name: string
}

export interface TeamJoinRequest {
  code: string
}

export interface TeamMemberResponse {
  id: string
  name: string
  email: string
  avatar_url?: string
  current_team?: boolean
  joined_at: string
  roles: RoleSimpleResponse[]
}

export interface TeamInviteRequest {
  email: string
}

export interface TeamSwitchResponse {
  message: string
  team_id: number
}

export interface UserTeamsListResponse {
  teams: TeamResponse[]
  current_team_id: number
}

export interface AssignRolesRequest {
  role_ids: number[]
}

export const teamApi = {
  createTeam: (data: TeamCreateRequest) => {
    return request.post<TeamResponse>('/v1/teams/', data)
  },

  joinTeam: (data: TeamJoinRequest) => {
    return request.post<TeamResponse>('/v1/teams/join', data)
  },

  getMyTeam: () => {
    return request.get<TeamResponse>('/v1/teams/me')
  },

  getUserTeams: () => {
    return request.get<UserTeamsListResponse>('/v1/teams/user-teams')
  },

  switchTeam: (teamId: number) => {
    return request.post<TeamSwitchResponse>('/v1/teams/switch', { team_id: teamId })
  },

  getTeamDetail: (teamId: number) => {
    return request.get<TeamResponse>(`/v1/teams/${teamId}`)
  },

  getTeamMembers: (teamId: number) => {
    return request.get<TeamMemberResponse[]>(`/v1/teams/${teamId}/members`)
  },

  inviteMember: (teamId: number, data: TeamInviteRequest) => {
    return request.post<{ message: string }>(`/v1/teams/${teamId}/invite`, data)
  },

  addMemberDirect: (teamId: number, userId: number) => {
    return request.post<{ message: string; user_id: number }>(`/v1/teams/${teamId}/members`, { user_id: userId })
  },

  removeMember: (teamId: number, userId: string) => {
    return request.delete<{ message: string }>(`/v1/teams/${teamId}/members/${userId}`)
  },

  regenerateInviteCode: (teamId: number) => {
    return request.post<{ code: string }>(`/v1/teams/${teamId}/regenerate-code`)
  },

  updateTeam: (teamId: number, data: { name?: string }) => {
    return request.put<TeamResponse>(`/v1/teams/${teamId}`, data)
  },

  assignMemberRoles: (teamId: number, userId: string, roleIds: number[]) => {
    return request.post<{ message: string; user_id: number; role_ids: number[] }>(
      `/v1/teams/${teamId}/members/${userId}/roles`,
      { role_ids: roleIds }
    )
  },

  getMemberRoles: (teamId: number, userId: string) => {
    return request.get<RoleSimpleResponse[]>(`/v1/teams/${teamId}/members/${userId}/roles`)
  }
}