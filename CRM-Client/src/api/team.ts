import request from '@/utils/request'
import {
  RoleSimpleResponseSchema,
  TeamResponseSchema,
  TeamMemberResponseSchema,
  TeamSwitchResponseSchema,
  UserTeamsListResponseSchema,
  TeamMessageResponseSchema,
  TeamMemberMutationResponseSchema,
  TeamInviteCodeResponseSchema,
  TeamAssignRolesResponseSchema,
  TeamUpdateMemberNameResponseSchema,
  type RoleSimpleResponse,
  type TeamResponse,
  type TeamMemberResponse,
  type TeamSwitchResponse,
  type UserTeamsListResponse,
  type TeamMessageResponse,
  type TeamMemberMutationResponse,
  type TeamInviteCodeResponse,
  type TeamAssignRolesResponse,
  type TeamUpdateMemberNameResponse,
} from '@/schemas/team'

export type {
  RoleSimpleResponse,
  TeamResponse,
  TeamMemberResponse,
  TeamSwitchResponse,
  UserTeamsListResponse,
} from '@/schemas/team'

export interface TeamCreateRequest {
  name: string
}

export interface TeamJoinRequest {
  code: string
}

export interface TeamInviteRequest {
  email: string
}

export interface AssignRolesRequest {
  role_ids: number[]
}

export interface ResetPasswordRequest {
  new_password: string
}

export interface UpdateMemberNameRequest {
  name: string
}

export const teamApi = {
  createTeam: async (data: TeamCreateRequest): Promise<TeamResponse> => {
    return TeamResponseSchema.parse(await request.post('/v1/teams/', data))
  },

  joinTeam: async (data: TeamJoinRequest): Promise<TeamResponse> => {
    return TeamResponseSchema.parse(await request.post('/v1/teams/join', data))
  },

  getMyTeam: async (): Promise<TeamResponse> => {
    return TeamResponseSchema.parse(await request.get('/v1/teams/me'))
  },

  getUserTeams: async (): Promise<UserTeamsListResponse> => {
    return UserTeamsListResponseSchema.parse(await request.get('/v1/teams/user-teams'))
  },

  switchTeam: async (teamId: number): Promise<TeamSwitchResponse> => {
    return TeamSwitchResponseSchema.parse(await request.post('/v1/teams/switch', { team_id: teamId }))
  },

  getTeamDetail: async (teamId: number): Promise<TeamResponse> => {
    return TeamResponseSchema.parse(await request.get(`/v1/teams/${teamId}`))
  },

  getTeamMembers: async (teamId: number): Promise<TeamMemberResponse[]> => {
    return TeamMemberResponseSchema.array().parse(await request.get(`/v1/teams/${teamId}/members`))
  },

  inviteMember: async (teamId: number, data: TeamInviteRequest): Promise<TeamMessageResponse> => {
    return TeamMessageResponseSchema.parse(await request.post(`/v1/teams/${teamId}/invite`, data))
  },

  addMemberDirect: async (teamId: number, userId: number): Promise<TeamMemberMutationResponse> => {
    return TeamMemberMutationResponseSchema.parse(
      await request.post(`/v1/teams/${teamId}/members`, { user_id: userId })
    )
  },

  removeMember: async (teamId: number, userId: number): Promise<TeamMessageResponse> => {
    return TeamMessageResponseSchema.parse(await request.delete(`/v1/teams/${teamId}/members/${userId}`))
  },

  regenerateInviteCode: async (teamId: number): Promise<TeamInviteCodeResponse> => {
    return TeamInviteCodeResponseSchema.parse(await request.post(`/v1/teams/${teamId}/regenerate-code`))
  },

  updateTeam: async (teamId: number, data: { name?: string }): Promise<TeamResponse> => {
    return TeamResponseSchema.parse(await request.put(`/v1/teams/${teamId}`, data))
  },

  assignMemberRoles: async (teamId: number, userId: number, roleIds: number[]): Promise<TeamAssignRolesResponse> => {
    return TeamAssignRolesResponseSchema.parse(
      await request.post(`/v1/teams/${teamId}/members/${userId}/roles`, { role_ids: roleIds })
    )
  },

  getMemberRoles: async (teamId: number, userId: number): Promise<RoleSimpleResponse[]> => {
    return RoleSimpleResponseSchema.array().parse(await request.get(`/v1/teams/${teamId}/members/${userId}/roles`))
  },

  // 重置成员密码（新增）
  resetMemberPassword: async (teamId: number, userId: number, data: ResetPasswordRequest): Promise<TeamMessageResponse> => {
    return TeamMessageResponseSchema.parse(
      await request.post(`/v1/teams/${teamId}/members/${userId}/reset-password`, data)
    )
  },

  updateMemberName: async (teamId: number, userId: number, data: UpdateMemberNameRequest): Promise<TeamUpdateMemberNameResponse> => {
    return TeamUpdateMemberNameResponseSchema.parse(
      await request.put(`/v1/teams/${teamId}/members/${userId}/name`, data)
    )
  }
}
