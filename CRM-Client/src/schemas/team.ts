import { z } from 'zod'

export const RoleSimpleResponseSchema = z.object({
  id: z.number(),
  name: z.string(),
  code: z.string(),
}).passthrough()

export const TeamResponseSchema = z.object({
  id: z.number(),
  name: z.string(),
  code: z.string(),
  // Preserve the existing client string representation and backend numeric IDs.
  owner_id: z.union([z.number(), z.string()]),
  created_at: z.string(),
  updated_at: z.string().optional(),
}).passthrough()

export const TeamMemberResponseSchema = z.object({
  id: z.number(),
  name: z.string(),
  email: z.string(),
  avatar_url: z.string().nullable().optional(),
  current_team: z.boolean().optional(),
  joined_at: z.string(),
  roles: z.array(RoleSimpleResponseSchema),
}).passthrough()

export const TeamSwitchResponseSchema = z.object({
  message: z.string(),
  team_id: z.number(),
}).passthrough()

export const UserTeamsListResponseSchema = z.object({
  teams: z.array(TeamResponseSchema),
  current_team_id: z.number().nullable(),
}).passthrough()

export const TeamMessageResponseSchema = z.object({
  message: z.string(),
}).passthrough()

export const TeamMemberMutationResponseSchema = TeamMessageResponseSchema.extend({
  user_id: z.number(),
})

export const TeamInviteCodeResponseSchema = z.object({
  code: z.string(),
}).passthrough()

export const TeamAssignRolesResponseSchema = TeamMemberMutationResponseSchema.extend({
  role_ids: z.array(z.number()),
})

export const TeamUpdateMemberNameResponseSchema = TeamMemberMutationResponseSchema.extend({
  name: z.string(),
})

export type RoleSimpleResponse = z.infer<typeof RoleSimpleResponseSchema>
export type TeamResponse = z.infer<typeof TeamResponseSchema>
export type TeamMemberResponse = z.infer<typeof TeamMemberResponseSchema>
export type TeamSwitchResponse = z.infer<typeof TeamSwitchResponseSchema>
export type UserTeamsListResponse = z.infer<typeof UserTeamsListResponseSchema>
export type TeamMessageResponse = z.infer<typeof TeamMessageResponseSchema>
export type TeamMemberMutationResponse = z.infer<typeof TeamMemberMutationResponseSchema>
export type TeamInviteCodeResponse = z.infer<typeof TeamInviteCodeResponseSchema>
export type TeamAssignRolesResponse = z.infer<typeof TeamAssignRolesResponseSchema>
export type TeamUpdateMemberNameResponse = z.infer<typeof TeamUpdateMemberNameResponseSchema>
